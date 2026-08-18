import struct, sys
from collections import defaultdict, Counter
def frames_of(path):
    raw=open(path,'rb').read()
    def unesc(f):
        out=bytearray(); esc=False
        for b in f:
            if esc: out.append(b^0x20); esc=False
            elif b==0x7D: esc=True
            else: out.append(b)
        return bytes(out)
    return [unesc(x) for x in raw.split(b'\x7e') if len(x)>2]
def journal(path):
    fr=frames_of(path)
    logs=sorted((int.from_bytes(f[8:16],'little'), f) for f in fr if f[0]==0x10 and len(f)>=16 and int.from_bytes(f[8:16],'little')>0x0100000000000000)
    p=[f for ts,f in logs if int.from_bytes(f[6:8],'little')==0x1843]
    dev=defaultdict(lambda:{'n':0,'res':0,'ops':Counter()})
    for f in p:
        body=f[16:][4:]
        for i in range(len(body)//28):
            r=body[i*28:(i+1)*28]
            if not any(r): continue
            ident,flags,a,b,c,ts=struct.unpack_from('<HHIIII',r,0)
            d=ident>>8
            if d==0 or flags not in (0x0400,0x0420): continue
            dev[d]['n']+=1; dev[d]['ops'][ident&0xff]+=1
            if b or c: dev[d]['res']+=1
    return len(p), dev
for path in sys.argv[1:]:
    n,dev=journal(path)
    print('=== %s: снимков 0x1843: %d ===' % (path.split('/')[-1], n))
    print('  устр | записей | с результатом')
    for d in sorted(dev): print('   %2d  | %5d   | %5d' % (d, dev[d]['n'], dev[d]['res']))
