#!/usr/bin/env python3
# Минимальный EFS2-клиент поверх DIAG: HELLO, затем чтение файла. Слушает порт, к которому подключается diag-router.
import socket, struct, sys, time, threading
HOST,PORT=sys.argv[1],int(sys.argv[2]); ACT=sys.argv[3] if len(sys.argv)>3 else 'hello'; PATH=sys.argv[4] if len(sys.argv)>4 else ''
def crc16(d):
    c=0xFFFF
    for b in d:
        c^=b
        for _ in range(8): c=(c>>1)^0x8408 if c&1 else c>>1
    return c^0xFFFF
def encap(p):
    f=p+crc16(p).to_bytes(2,'little'); o=bytearray()
    for b in f:
        if b in (0x7D,0x7E): o+=bytes([0x7D,b^0x20])
        else: o.append(b)
    o.append(0x7E); return bytes(o)
def unesc(f):
    o=bytearray(); e=False
    for b in f:
        if e: o.append(b^0x20); e=False
        elif b==0x7D: e=True
        else: o.append(b)
    return bytes(o)
srv=socket.socket(); srv.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1); srv.bind((HOST,PORT)); srv.listen(1)
print('жду роутер на %s:%d'%(HOST,PORT),flush=True); s,_=srv.accept(); print('роутер подключился',flush=True)
buf=bytearray(); frames=[]
def rd():
    while True:
        try: d=s.recv(65536)
        except OSError: return
        if not d: print('!!! роутер закрыл соединение',flush=True); return
        buf.extend(d)
        while 0x7E in buf:
            i=buf.index(0x7E); fr=unesc(bytes(buf[:i])); del buf[:i+1]
            if len(fr)>2: frames.append(fr)
threading.Thread(target=rd,daemon=True).start()
def send(name,p,wait=0.6): print('  -> %s'%name,flush=True); s.send(encap(p)); time.sleep(wait)
EFS=0x13  # DIAG_SUBSYS_FS
send('version', b'\x00')
# EFS2 HELLO: 4B 13 0000 + 6 x u32 (targ_pkt_window, targ_byte_window, host_pkt_window, host_byte_window, iter_pkt_window, version) + min_version + feature_bits
send('EFS2_HELLO', bytes([0x4B,EFS]) + struct.pack('<H6I3II', 0, 0x100000,0x100000,0x100000,0x100000,0x100000,0x100000, 1,1,1, 0))
def lsdir(PATH):
    send('EFS2_OPENDIR '+PATH, bytes([0x4B,EFS,0x0B,0x00]) + PATH.encode()+b'\0')
    time.sleep(1)
    if frames and frames[-1][0]==0x4B and len(frames[-1])>=12:
        dirp=struct.unpack_from('<I',frames[-1],4)[0]
        for seq in range(1,40):
            send('EFS2_READDIR %d'%seq, bytes([0x4B,EFS,0x0C,0x00]) + struct.pack('<II',dirp,seq))
            fr=frames[-1] if frames else b''
            if fr and fr[0]==0x4B and len(fr)>=40:
                name=fr[40:].split(b'\0')[0]
                et=struct.unpack_from('<I',fr,16)[0]
                print('     entry: %s type=%d' % (name.decode('ascii','replace'), et), flush=True)
                if not name: break
        send('EFS2_CLOSEDIR', bytes([0x4B,EFS,0x0D,0x00]) + struct.pack('<I',dirp))
if ACT=='ls' and PATH:
    for P in PATH.split(';'): lsdir(P)
elif ACT=='stat' and PATH:
    plist = open(PATH).read().split() if PATH.startswith('/tmp/') else PATH.split(';')
    for P in plist:
        send('OPEN '+P, bytes([0x4B,EFS,0x02,0x00]) + struct.pack('<II',0,0) + P.encode()+b'\0')
        fr=frames[-1] if frames else b''
        if fr and fr[0]==0x4B and len(fr)>=12:
            fd,err=struct.unpack_from('<iI',fr,4)
            if fd>=0:
                send('READ', bytes([0x4B,EFS,0x04,0x00]) + struct.pack('<III',fd,64,0))
                fr2=frames[-1]; data=fr2[20:] if len(fr2)>20 else b''
                print('     %s: ЕСТЬ, %d байт: %s' % (P, len(data), data[:16].hex(' ')), flush=True)
                send('CLOSE', bytes([0x4B,EFS,0x03,0x00]) + struct.pack('<i',fd))
            else:
                print('     %s: нет (errno %d)' % (P, err), flush=True)
elif ACT=='nvread' and PATH:
    # NV_READ 0x26: item(2) + data(128) + status(2)
    for item in [int(x) for x in PATH.split(',')]:
        send('NV_READ %d' % item, bytes([0x26]) + struct.pack('<H', item) + b'\0'*128 + b'\0\0', wait=1.0)
        fr=frames[-1] if frames else b''
        if fr and fr[0]==0x26 and len(fr)>=133:
            status=struct.unpack_from('<H',fr,131)[0]; data=fr[3:3+16]
            print('     NV %d: status=%d data=%s' % (item, status, data.hex(' ')), flush=True)
        else:
            print('     NV %d: ответ %s' % (item, fr[:8].hex(' ') if fr else 'нет'), flush=True)
elif ACT=='put' and PATH:
    # PATH = "<efs path>:<hex bytes>"
    P,hexdata=PATH.split(':',1); data=bytes.fromhex(hexdata)
    # прочитать старое
    send('OPEN(r) '+P, bytes([0x4B,EFS,0x02,0x00]) + struct.pack('<II',0,0) + P.encode()+b'\0', wait=1.0)
    fr=frames[-1]; fd,err=struct.unpack_from('<iI',fr,4)
    if fd>=0:
        send('READ', bytes([0x4B,EFS,0x04,0x00]) + struct.pack('<III',fd,64,0), wait=1.0)
        old=frames[-1][20:]; print('     старое: %s' % old.hex(' '), flush=True)
        send('CLOSE', bytes([0x4B,EFS,0x03,0x00]) + struct.pack('<i',fd), wait=1.0)
    else:
        print('     файла не было (errno %d)' % err, flush=True)
    # O_WRONLY|O_CREAT|O_TRUNC = 1|0x40|0x200 = 0x241 ; mode 0644
    send('OPEN(w) '+P, bytes([0x4B,EFS,0x02,0x00]) + struct.pack('<II',0x241,0o644) + P.encode()+b'\0', wait=1.0)
    fr=frames[-1]; fd,err=struct.unpack_from('<iI',fr,4); print('     open(w) fd=%d err=%d' % (fd,err), flush=True)
    if fd>=0:
        # WRITE: 4B 13 0500 fd(4) offset(4) data
        send('WRITE', bytes([0x4B,EFS,0x05,0x00]) + struct.pack('<Ii',fd,0) + data, wait=1.0)
        fr=frames[-1]; print('     write resp: %s' % fr[:16].hex(' '), flush=True)
        send('CLOSE', bytes([0x4B,EFS,0x03,0x00]) + struct.pack('<i',fd), wait=1.0)
        # проверка
        send('OPEN(r2) '+P, bytes([0x4B,EFS,0x02,0x00]) + struct.pack('<II',0,0) + P.encode()+b'\0', wait=1.0)
        fd2,_=struct.unpack_from('<iI',frames[-1],4)
        if fd2>=0:
            send('READ', bytes([0x4B,EFS,0x04,0x00]) + struct.pack('<III',fd2,64,0), wait=1.0)
            print('     новое: %s' % frames[-1][20:].hex(' '), flush=True)
            send('CLOSE', bytes([0x4B,EFS,0x03,0x00]) + struct.pack('<i',fd2), wait=1.0)
        # SYNC (не обязательно): 4B 13 3400? пропускаем; EFS2 write синхронен
elif ACT=='get' and PATH:
    # OPEN: 4B 13 0200 oflag(4) mode(4) path\0 ; O_RDONLY=0
    send('EFS2_OPEN', bytes([0x4B,EFS,0x02,0x00]) + struct.pack('<II',0,0) + PATH.encode()+b'\0')
    fr=frames[-1] if frames else b''
    if fr and fr[0]==0x4B and len(fr)>=12:
        fd,err=struct.unpack_from('<iI',fr,4); print('     fd=%d err=%d'%(fd,err),flush=True)
        if fd>=0:
            send('EFS2_READ', bytes([0x4B,EFS,0x04,0x00]) + struct.pack('<III',fd,256,0))
            fr=frames[-1]; print('     read:', fr[16:16+32].hex(' '), flush=True)
            send('EFS2_CLOSE', bytes([0x4B,EFS,0x03,0x00]) + struct.pack('<i',fd))
time.sleep(2); print('всего кадров:',len(frames),flush=True)
