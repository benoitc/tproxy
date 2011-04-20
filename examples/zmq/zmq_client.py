import gevent
import socket
import time

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

sock.connect(("127.0.0.1", 5000))

def send(sock):
    for i in range(10):
        msg = "hello %s\n" % i
        print "Send %s" % msg
        sock.sendall(msg)
        time.sleep(0.1)

gsend = gevent.spawn(send, sock)


def client_listen(sock):
    
    buf = ""
    while True:
        data = sock.recv(8192)
        if not data:
            break
        print "got %s" % data 

glisten = gevent.spawn(client_listen, sock)

try:
    gevent.joinall([gsend, glisten]) 
except KeyboardInterrupt:
    sys.exit(0)
