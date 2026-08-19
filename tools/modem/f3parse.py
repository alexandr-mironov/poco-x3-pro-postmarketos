#!/usr/bin/env python3
"""Decode F3 (debug text) messages from a DIAG capture made by diagcli.py.

Handles DIAG_EXT_MSG_F (0x79, format string in the packet) and
DIAG_QSR_EXT_MSG_TERSE_F (0x92, QShrink: only a hash, resolved through the
qdsp6m.qdb shipped with the modem firmware).

    f3parse.py <capture.bin> [qdsp6m.qdb] [-n LAST] [-g REGEX]

Prints "<seconds> <ssid>/<line> <file>: <text>"; seconds are relative to the
first message. Without the qdb, 0x92 messages are shown as "hash=N args=...".
"""
import argparse
import re
import struct
import sys
import zlib


def unescape(frame):
    out = bytearray()
    esc = False
    for b in frame:
        if esc:
            out.append(b ^ 0x20)
            esc = False
        elif b == 0x7D:
            esc = True
        else:
            out.append(b)
    return bytes(out)


def frames(data):
    for raw in data.split(b'\x7e'):
        if len(raw) > 2:
            yield unescape(raw)[:-2]  # drop CRC


def load_qdb(path):
    d = open(path, 'rb').read()
    if d[:5] != b'\x7fQDBB':
        raise SystemExit('%s: not a QShrink db' % path)
    txt = zlib.decompress(d[0x40:]).decode('latin-1')
    db = {}
    started = False
    for line in txt.split('\n'):
        if not started:
            started = line.startswith('<Content>')
            continue
        parts = line.split(':', 5)
        if len(parts) < 6:
            continue
        try:
            db[int(parts[0])] = (parts[4], parts[5])
        except ValueError:
            continue
    return db


def fmt_msg(fmt, args):
    # C printf → python %, best effort: %d %u %x %X %c %s %p %ld %lu %lld %08x ...
    fmt = fmt.replace('%%', '\x00')
    spec = re.compile(r'%([-+ #0]*)(\d*|\*)(?:\.(\d+|\*))?(hh|h|ll|l|z|j|t|L)?([diouxXcspeEfgG])')
    out = []
    pos = 0
    ai = 0
    for m in spec.finditer(fmt):
        out.append(fmt[pos:m.start()])
        pos = m.end()
        conv = m.group(5)
        a = args[ai] if ai < len(args) else None
        ai += 1
        if a is None:
            out.append('%' + conv)
            continue
        flags, width, prec = m.group(1), m.group(2), m.group(3)
        if conv in 'di':
            if a >= 0x80000000:
                a -= 0x100000000
            out.append(('%' + flags + width + 'd') % a)
        elif conv in 'uoxX':
            out.append(('%' + flags + width + conv) % a)
        elif conv == 'c':
            out.append(chr(a & 0xff) if 32 <= (a & 0xff) < 127 else '?')
        elif conv in 'sp':
            out.append('0x%x' % a)
        elif conv in 'eEfgG':
            out.append('%g' % struct.unpack('<f', struct.pack('<I', a))[0])
        else:
            out.append('%' + conv)
    out.append(fmt[pos:])
    return ''.join(out).replace('\x00', '%')


def parse(data, db):
    msgs = []
    for f in frames(data):
        if not f:
            continue
        cmd = f[0]
        if cmd == 0x79 and len(f) >= 20:
            ts_type, nargs, drop = f[1], f[2], f[3]
            ts, line, ssid, mask = struct.unpack_from('<QHHI', f, 4)
            off = 20
            if len(f) < off + 4 * nargs:
                continue
            args = list(struct.unpack_from('<%dI' % nargs, f, off)) if nargs else []
            off += 4 * nargs
            rest = f[off:].split(b'\x00')
            fmt = rest[0].decode('latin-1') if rest else ''
            fname = rest[1].decode('latin-1') if len(rest) > 1 else ''
            msgs.append((ts, ssid, line, fname, fmt_msg(fmt, args)))
        elif cmd == 0x92 and len(f) >= 24:
            ts_type, nargs, drop = f[1], f[2], f[3]
            ts, line, ssid, mask, h = struct.unpack_from('<QHHII', f, 4)
            off = 24
            args = list(struct.unpack_from('<%dI' % nargs, f, off)) if len(f) >= off + 4 * nargs else []
            if db and h in db:
                fname, fmt = db[h]
                # the qdb line overrides the packet's file name; keep packet line no.
                msgs.append((ts, ssid, line, fname, fmt_msg(fmt, args)))
            else:
                msgs.append((ts, ssid, line, '?', 'hash=%d args=%s' % (h, ' '.join('0x%x' % a for a in args))))
    return msgs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('capture')
    ap.add_argument('qdb', nargs='?')
    ap.add_argument('-n', type=int, default=0, help='print only the last N messages')
    ap.add_argument('-g', help='regex filter (case-insensitive) on file/text')
    ap.add_argument('--ssid', type=int, help='only this SSID')
    a = ap.parse_args()
    db = load_qdb(a.qdb) if a.qdb else None
    msgs = parse(open(a.capture, 'rb').read(), db)
    if a.ssid is not None:
        msgs = [m for m in msgs if m[1] == a.ssid]
    if a.g:
        rx = re.compile(a.g, re.I)
        msgs = [m for m in msgs if rx.search(m[3]) or rx.search(m[4])]
    if a.n:
        msgs = msgs[-a.n:]
    t0 = msgs[0][0] if msgs else 0
    # DIAG timestamp: upper 48 bits are 1.25 ms units
    for ts, ssid, line, fname, text in msgs:
        sec = ((ts - t0) >> 16) * 1.25 / 1000.0
        print('%9.3f %5d/%-5d %-32s %s' % (sec, ssid, line, fname[:32], text))
    print('# %d messages' % len(msgs), file=sys.stderr)


if __name__ == '__main__':
    main()
