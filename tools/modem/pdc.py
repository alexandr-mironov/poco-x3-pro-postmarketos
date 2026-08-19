#!/usr/bin/env python3
"""Minimal QMI PDC (Persistent Device Configuration) client over QRTR.

Loads and activates MCFG MBN files (mcfg_hw.mbn / mcfg_sw.mbn) the way the
Android RIL does. qmicli 1.39 cannot: its --pdc-load-config frees the mmap'd
file (segfault) and hard-codes the SOFTWARE type, so platform (hw) configs
are impossible with it.

    pdc.py list [platform|software]
    pdc.py load <file> [platform|software]      -> prints the config id
    pdc.py select <platform|software> <hexid>
    pdc.py activate <platform|software>         -> the modem restarts itself
    pdc.py loadact <file> <platform|software>   -> load + select + activate
    pdc.py delete <platform|software> <hexid>
    pdc.py deactivate <platform|software>

Run as root on the phone. Needs the modem running; one command at a time.
"""
import hashlib
import socket
import struct
import sys
import time

AF_QIPCRTR = 42
QRTR_PORT_CTRL = 42
QRTR_TYPE_NEW_SERVER = 4
QRTR_TYPE_NEW_LOOKUP = 10
PDC_SERVICE = 36

CFG = {'platform': 0, 'software': 1}
CHUNK = 0x400

MSG_REGISTER = 0x20
MSG_GET_SELECTED = 0x22
MSG_SET_SELECTED = 0x23
MSG_LIST = 0x24
MSG_DELETE = 0x25
MSG_LOAD = 0x26
MSG_ACTIVATE = 0x27
MSG_DEACTIVATE = 0x2B


def tlv(t, payload):
    return struct.pack('<BH', t, len(payload)) + payload


def parse_tlvs(buf):
    out = {}
    i = 0
    while i + 3 <= len(buf):
        t, ln = struct.unpack_from('<BH', buf, i)
        out[t] = buf[i + 3:i + 3 + ln]
        i += 3 + ln
    return out


class Pdc:
    def __init__(self):
        self.s = socket.socket(AF_QIPCRTR, socket.SOCK_DGRAM)
        self.s.settimeout(5)
        # autobind by sending a lookup to the name server
        node, port = self.lookup()
        self.addr = (node, port)
        self.txn = 1

    def lookup(self):
        """Find the PDC service on the bus.

        Sending the lookup to the in-kernel name server (local node, port 42)
        fails with ENODEV from plain sockets on this kernel, so ask libqmi:
        `qmicli -v` prints every server it sees during its own lookup.
        """
        import re
        import subprocess
        out = subprocess.run(['qmicli', '-v', '-d', 'qrtr://0', '--dms-noop'],
                             capture_output=True, text=True, timeout=30)
        for m in re.finditer(r'added server on (\d+):(\d+) -> service (\d+)', out.stdout + out.stderr):
            node, port, svc = map(int, m.groups())
            if svc == PDC_SERVICE:
                return node, port
        raise SystemExit('PDC service not found on QRTR')

    def send(self, msg_id, payload):
        txn = self.txn
        self.txn += 1
        hdr = struct.pack('<BHHH', 0, txn, msg_id, len(payload))
        self.s.sendto(hdr + payload, self.addr)
        return txn

    def recv(self, want_msg, want_txn=None, want_ind=False, timeout=10):
        """Wait for a response (want_txn) or an indication (want_ind) for msg."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                data, addr = self.s.recvfrom(65536)
            except socket.timeout:
                continue
            if addr != self.addr or len(data) < 7:
                continue
            flags, txn, msg_id, ln = struct.unpack_from('<BHHH', data, 0)
            body = parse_tlvs(data[7:7 + ln])
            if msg_id != want_msg:
                continue
            if flags == 2 and not want_ind and txn == want_txn:
                return body
            if flags == 4 and want_ind:
                return body
        raise SystemExit('timeout waiting for 0x%02x %s' % (want_msg, 'ind' if want_ind else 'rsp'))

    @staticmethod
    def result(body):
        if 2 in body:
            r, e = struct.unpack('<HH', body[2][:4])
            return r, e
        return None, None

    @staticmethod
    def ind_result(body):
        if 1 in body:
            return struct.unpack('<H', body[1][:2])[0]
        return None

    def token(self, tok):
        return tlv(0x10, struct.pack('<I', tok))

    def register(self):
        txn = self.send(MSG_REGISTER, tlv(0x10, b'\x01') + tlv(0x11, b'\x01'))
        body = self.recv(MSG_REGISTER, txn)
        return self.result(body)

    def list(self, ctype):
        txn = self.send(MSG_LIST, self.token(txn_tok()) + tlv(0x11, struct.pack('<I', CFG[ctype])))
        r = self.result(self.recv(MSG_LIST, txn))
        print('list %s: result %s' % (ctype, r))
        if r[0] != 0:
            return []
        body = self.recv(MSG_LIST, want_ind=True)
        ids = []
        if 0x11 in body:
            b = body[0x11]
            n = b[0]
            i = 1
            for _ in range(n):
                t = struct.unpack_from('<I', b, i)[0]
                ln = b[i + 4]
                cid = b[i + 5:i + 5 + ln]
                ids.append((t, cid))
                i += 5 + ln
        print('  indication result %s, %d configs' % (self.ind_result(body), len(ids)))
        for t, cid in ids:
            print('   type %d id %s' % (t, cid.hex()))
        return ids

    def get_selected(self, ctype):
        txn = self.send(MSG_GET_SELECTED, tlv(0x01, struct.pack('<I', CFG[ctype])) + self.token(txn_tok()))
        r = self.result(self.recv(MSG_GET_SELECTED, txn))
        print('get-selected %s: result %s' % (ctype, r))
        if r[0] != 0:
            return
        body = self.recv(MSG_GET_SELECTED, want_ind=True)
        print('  indication result %s active %s pending %s' % (
            self.ind_result(body),
            body.get(0x11, b'')[1:].hex() if 0x11 in body else '-',
            body.get(0x12, b'')[1:].hex() if 0x12 in body else '-'))

    def load(self, path, ctype):
        data = open(path, 'rb').read()
        cid = hashlib.sha1(data).digest()
        total = len(data)
        off = 0
        print('load %s (%d bytes) as %s, id %s' % (path, total, ctype, cid.hex()))
        while off < total:
            chunk = data[off:off + CHUNK]
            seq = struct.pack('<I', CFG[ctype]) + struct.pack('<B', len(cid)) + cid \
                + struct.pack('<I', total) + struct.pack('<H', len(chunk)) + chunk
            txn = self.send(MSG_LOAD, tlv(0x01, seq) + self.token(txn_tok()))
            r = self.result(self.recv(MSG_LOAD, txn))
            if r[0] != 0:
                raise SystemExit('load chunk @%d failed: %s' % (off, r))
            body = self.recv(MSG_LOAD, want_ind=True)
            ir = self.ind_result(body)
            rem = struct.unpack('<I', body[0x12])[0] if 0x12 in body else None
            reset = body.get(0x13, b'\x00')[0]
            if ir != 0:
                raise SystemExit('load indication @%d: error %s (remaining %s, frame_reset %s)' % (off, ir, rem, reset))
            if reset:
                print('  frame reset requested, restarting from 0')
                off = 0
                continue
            off += len(chunk)
            print('  %d/%d, remaining %s' % (off, total, rem))
            if rem == 0:
                break
        print('loaded, id %s' % cid.hex())
        return cid

    def select(self, ctype, cid):
        seq = struct.pack('<I', CFG[ctype]) + struct.pack('<B', len(cid)) + cid
        txn = self.send(MSG_SET_SELECTED, tlv(0x01, seq) + self.token(txn_tok()))
        r = self.result(self.recv(MSG_SET_SELECTED, txn))
        print('set-selected %s %s: result %s' % (ctype, cid.hex(), r))
        if r[0] != 0:
            raise SystemExit('set-selected failed')
        body = self.recv(MSG_SET_SELECTED, want_ind=True)
        print('  indication result %s' % self.ind_result(body))

    def activate(self, ctype):
        txn = self.send(MSG_ACTIVATE, tlv(0x01, struct.pack('<I', CFG[ctype])) + self.token(txn_tok()))
        r = self.result(self.recv(MSG_ACTIVATE, txn))
        print('activate %s: result %s' % (ctype, r))
        if r[0] != 0:
            raise SystemExit('activate failed')
        try:
            body = self.recv(MSG_ACTIVATE, want_ind=True, timeout=15)
            print('  indication result %s' % self.ind_result(body))
        except SystemExit as e:
            print('  (no indication: %s — the modem may be restarting)' % e)

    def deactivate(self, ctype):
        txn = self.send(MSG_DEACTIVATE, tlv(0x01, struct.pack('<I', CFG[ctype])) + self.token(txn_tok()))
        r = self.result(self.recv(MSG_DEACTIVATE, txn))
        print('deactivate %s: result %s' % (ctype, r))
        if r[0] == 0:
            body = self.recv(MSG_DEACTIVATE, want_ind=True, timeout=15)
            print('  indication result %s' % self.ind_result(body))

    def delete(self, ctype, cid):
        txn = self.send(MSG_DELETE, tlv(0x01, struct.pack('<I', CFG[ctype])) + self.token(txn_tok())
                        + tlv(0x11, struct.pack('<B', len(cid)) + cid))
        r = self.result(self.recv(MSG_DELETE, txn))
        print('delete %s %s: result %s' % (ctype, cid.hex(), r))
        if r[0] == 0:
            body = self.recv(MSG_DELETE, want_ind=True)
            print('  indication result %s' % self.ind_result(body))


_tok = [0]


def txn_tok():
    _tok[0] += 1
    return _tok[0]


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    cmd = sys.argv[1]
    p = Pdc()
    print('PDC at node %d port %d' % p.addr)
    p.register()
    if cmd == 'list':
        p.list(sys.argv[2] if len(sys.argv) > 2 else 'platform')
    elif cmd == 'selected':
        p.get_selected(sys.argv[2] if len(sys.argv) > 2 else 'platform')
    elif cmd == 'load':
        p.load(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else 'platform')
    elif cmd == 'select':
        p.select(sys.argv[2], bytes.fromhex(sys.argv[3]))
    elif cmd == 'activate':
        p.activate(sys.argv[2])
    elif cmd == 'deactivate':
        p.deactivate(sys.argv[2])
    elif cmd == 'delete':
        p.delete(sys.argv[2], bytes.fromhex(sys.argv[3]))
    elif cmd == 'loadact':
        ctype = sys.argv[3] if len(sys.argv) > 3 else 'platform'
        cid = p.load(sys.argv[2], ctype)
        time.sleep(1)
        p.select(ctype, cid)
        time.sleep(1)
        p.activate(ctype)
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
