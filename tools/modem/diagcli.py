#!/usr/bin/env python3
"""Минимальный клиент DIAG поверх TCP для отладки issue #1.

Слушает порт, к которому подключается diag-router, шлёт выбранные команды
и пишет всё принятое в файл, вытаскивая печатный текст.

  diagcli.py <адрес> <порт> <файл> <секунд> <шаги через запятую>

шаги: ver | ssid | setall | logrange | logall | events
"""
import socket, sys, time, threading, re

HOST, PORT = sys.argv[1], int(sys.argv[2])
OUT = sys.argv[3] if len(sys.argv) > 3 else '/var/log/diag-capture.bin'
SECONDS = int(sys.argv[4]) if len(sys.argv) > 4 else 60
STEPS = (sys.argv[5] if len(sys.argv) > 5 else 'ver').split(',')

def crc16(data):
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    return crc ^ 0xFFFF

def encap(payload):
    frame = payload + crc16(payload).to_bytes(2, 'little')
    out = bytearray()
    for b in frame:
        if b in (0x7D, 0x7E):
            out += bytes([0x7D, b ^ 0x20])
        else:
            out.append(b)
    out.append(0x7E)
    return bytes(out)

def unescape(frame):
    out = bytearray(); esc = False
    for b in frame:
        if esc:
            out.append(b ^ 0x20); esc = False
        elif b == 0x7D:
            esc = True
        else:
            out.append(b)
    return bytes(out)

srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind((HOST, PORT)); srv.listen(1)
print('жду diag-router на %s:%d' % (HOST, PORT), flush=True)
s, addr = srv.accept()
print('подключился %s' % (addr,), flush=True)

buf = bytearray(); frames = []; stop = False

def reader():
    global stop
    f = open(OUT, 'wb')
    while not stop:
        try:
            data = s.recv(65536)
        except OSError:
            break
        if not data:
            print('!!! роутер закрыл соединение', flush=True); break
        f.write(data); f.flush(); buf.extend(data)
        while 0x7E in buf:
            i = buf.index(0x7E)
            frame = unescape(bytes(buf[:i])); del buf[:i + 1]
            if len(frame) <= 2:
                continue
            frames.append(frame)
            if frame[0] in (0x13, 0x14, 0x15):
                why = {0x13: 'не поддержана', 0x14: 'неверный параметр', 0x15: 'неверная длина'}[frame[0]]
                print('  отказ (%s) на %02X' % (why, frame[1] if len(frame) > 1 else 0), flush=True)
                continue
            text = re.findall(rb'[ -~]{6,}', frame)
            if text:
                print('  [%02X] %s' % (frame[0], b' | '.join(text[:4]).decode('ascii', 'replace')), flush=True)
            elif frame[0] in (0x79, 0x92):
                print('  [%02X] F3-сообщение, %d байт (текста нет)' % (frame[0], len(frame)), flush=True)
            elif frame[0] == 0x10 and len(frame) >= 12:
                code = int.from_bytes(frame[6:8], 'little')
                print('  [10] лог 0x%04X, %d байт' % (code, len(frame)), flush=True)
    f.close()

threading.Thread(target=reader, daemon=True).start()

def send(name, payload):
    print('--- %s ---' % name, flush=True)
    try:
        s.send(encap(payload))
    except OSError as e:
        print('    отправить не удалось: %s' % e, flush=True); return False
    time.sleep(3)
    return True

for step in STEPS:
    if step == 'ver':
        send('версия (0x00)', b'\x00')
    elif step == 'ssid':
        send('диапазоны SSID (0x7D op1)', bytes([0x7D, 0x01]))
    elif step == 'setall':
        send('все маски F3 (0x7D op5)', bytes([0x7D, 0x05, 0x00]) + (0xFFFFFFFF).to_bytes(4, 'little'))
    elif step == 'logrange':
        send('диапазоны журналов (0x73 op1)', bytes([0x73, 0, 0, 0]) + (1).to_bytes(4, 'little'))
    elif step == 'logall':
        # 0x73 op3 = set mask; equip_id, num_items, then a bitmask with every bit set.
        # Log codes are 16-bit: equip_id in the high nibble, item in the low 12 bits.
        # We enable everything under equip 1 (WCDMA/LTE/RF ranges live there) and 0xB (LTE).
        for equip, nitems in ((0x1, 0x1A02), (0xB, 0x0200), (0x4, 0x0300), (0x7, 0x0300)):
            mask = b'\xff' * ((nitems + 7) // 8)
            payload = bytes([0x73, 0, 0, 0]) + (3).to_bytes(4, 'little') + equip.to_bytes(4, 'little') + nitems.to_bytes(4, 'little') + mask
            send('все логи, equip 0x%X (%d items)' % (equip, nitems), payload)
    elif step == 'events':
        send('события (0x60)', bytes([0x60, 0x01]))

print('--- слушаю %d с ---' % SECONDS, flush=True)
time.sleep(SECONDS)
stop = True
print('кадров принято: %d' % len(frames), flush=True)
