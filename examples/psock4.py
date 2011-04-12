import socket
import struct

def proxy(data):
    if len(data) < 9:
        return

    command = ord(data[1])
    ip, port = socket.inet_ntoa(data[4:8]), struct.unpack(">H", data[2:4])[0]
    idx = data.index("\0")
    userid = data[8:idx]

    if command == 1: #connect
        return dict(remote="%s:%s" % (ip, port),
                reply="\0\x5a\0\0\0\0\0\0",
                data=data[idx:])
    else:
        return {"close": "\0\x5b\0\0\0\0\0\0"}
