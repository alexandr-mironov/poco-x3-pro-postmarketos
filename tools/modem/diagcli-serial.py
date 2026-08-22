#!/usr/bin/env python3
"""DIAG client over a serial/USB device (for capturing on Android/MIUI).

Same DIAG protocol as diagcli.py, but instead of accepting a TCP connection
from our pmOS diag-router, it talks directly to a Qualcomm DIAG character
device — the /dev/ttyUSB* that appears once the phone's "diag" USB function is
enabled (e.g. dialer code *#*#717717#*#* on Xiaomi), or /dev/diag on a rooted
shell.

  diagcli-serial.py <device> <outfile> <seconds> <steps-comma-separated>

steps: ver | ssid | setall | logrange | logall | events   (as in diagcli.py)

Writes the raw HDLC stream to <outfile>; decode it with f3parse.py exactly like
a pmOS capture (same modem build => same messages, same QSR table).
"""
import os, sys, time, threading, re, termios, tty

DEV = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else 'diag-android.bin'
SECONDS = int(sys.argv[3]) if len(sys.argv) > 3 else 60
STEPS = (sys.argv[4] if len(sys.argv) > 4 else 'ver,ssid,setall,logall').split(',')


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


# open the char device in raw mode
fd = os.open(DEV, os.O_RDWR | os.O_NOCTTY)
try:
    tty.setraw(fd)
    attrs = termios.tcgetattr(fd)
    attrs[2] = attrs[2] & ~termios.CRTSCTS
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
except Exception as e:
    print('warn: not a tty (%s), continuing raw' % e, flush=True)

buf = bytearray(); frames = []; stop = False
f = open(OUT, 'wb')


def reader():
    while not stop:
        try:
            data = os.read(fd, 65536)
        except OSError:
            break
        if not data:
            time.sleep(0.01); continue
        f.write(data); f.flush(); buf.extend(data)
        while 0x7E in buf:
            i = buf.index(0x7E)
            frame = unescape(bytes(buf[:i])); del buf[:i + 1]
            if len(frame) <= 2:
                continue
            frames.append(frame)
            if frame[0] in (0x13, 0x14, 0x15):
                why = {0x13: 'unsupported', 0x14: 'bad param', 0x15: 'bad length'}[frame[0]]
                print('  reject (%s) on %02X' % (why, frame[1] if len(frame) > 1 else 0), flush=True)
                continue
            text = re.findall(rb'[ -~]{6,}', frame)
            if text:
                print('  [%02X] %s' % (frame[0], b' | '.join(text[:4]).decode('ascii', 'replace')), flush=True)
            elif frame[0] in (0x79, 0x92):
                pass  # F3, counted; decoded later by f3parse


threading.Thread(target=reader, daemon=True).start()


def send(name, payload):
    print('--- %s ---' % name, flush=True)
    try:
        os.write(fd, encap(payload))
    except OSError as e:
        print('    send failed: %s' % e, flush=True); return False
    time.sleep(3)
    return True


for step in STEPS:
    if step == 'ver':
        send('version (0x00)', b'\x00')
    elif step == 'ssid':
        send('SSID ranges (0x7D op1)', bytes([0x7D, 0x01]))
    elif step == 'setall':
        send('all F3 masks (0x7D op5)', bytes([0x7D, 0x05, 0x00]) + (0xFFFFFFFF).to_bytes(4, 'little'))
    elif step == 'logrange':
        send('log ranges (0x73 op1)', bytes([0x73, 0, 0, 0]) + (1).to_bytes(4, 'little'))
    elif step == 'logall':
        for equip, nitems in ((0x1, 0x1A02), (0xB, 0x0200), (0x4, 0x0300), (0x7, 0x0300)):
            mask = b'\xff' * ((nitems + 7) // 8)
            payload = bytes([0x73, 0, 0, 0]) + (3).to_bytes(4, 'little') + equip.to_bytes(4, 'little') + nitems.to_bytes(4, 'little') + mask
            send('all logs, equip 0x%X (%d items)' % (equip, nitems), payload)
    elif step == 'events':
        send('events (0x60)', bytes([0x60, 0x01]))

print('--- listening %d s ---' % SECONDS, flush=True)
time.sleep(SECONDS)
stop = True
time.sleep(0.3)
f.close()
print('frames received: %d' % len(frames), flush=True)
