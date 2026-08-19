import socket, threading, select
def serve(port):
    s=socket.socket(); s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1); s.bind(('0.0.0.0',port)); s.listen(5); return s
rs=serve(2500); cs=serve(2501)
router,_=rs.accept()           # diag-router подключается один раз и навсегда
client=None; lock=threading.Lock()
def from_router():
    global client
    while True:
        d=router.recv(65536)
        if not d: return
        with lock:
            if client:
                try: client.sendall(d)
                except Exception: client=None
threading.Thread(target=from_router,daemon=True).start()
while True:
    c,_=cs.accept()
    with lock: client=c
    try:
        while True:
            d=c.recv(65536)
            if not d: break
            router.sendall(d)
    except Exception: pass
    with lock:
        if client is c: client=None
    try: c.close()
    except Exception: pass
