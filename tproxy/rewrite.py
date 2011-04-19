# -*- coding: utf-8 -
#
# This file is part of tproxy released under the MIT license. 
# See the NOTICE for more information.

import sys

# backports socketio
import io
import socket

try:
    import errno
except ImportError:
    errno = None
EBADF = getattr(errno, 'EBADF', 9)
EINTR = getattr(errno, 'EINTR', 4)
EAGAIN = getattr(errno, 'EAGAIN', 11)
EWOULDBLOCK = getattr(errno, 'EWOULDBLOCK', 11)

_blocking_errnos = ( EAGAIN, EWOULDBLOCK, EBADF)

if sys.version_info < (2, 7, 0, 'final'):
    # in python 2.6 socket.recv_into doesn't support bytesarray
    import array
    def _readinto(sock, b):
        buf = array.array('c', ' ' * len(b))
        while True:
            try:
                recved = sock.recv_into(buf)
                b[0:recved] = buf.tostring()
                return recved
            except socket.error as e:
                n = e.args[0]
                
                if n == EINTR:
                    continue
                if n in _blocking_errnos:
                    return None
                raise

    def _write(sock, b):
        try:
            return sock.send(bytes(b))
        except socket.error as e:
            # XXX what about EINTR?
            if e.args[0] in _blocking_errnos:
                return None
            raise
else:
    _readinto = None
    _write = None


class RewriteIO(io.RawIOBase):

    """Raw I/O implementation for stream sockets.

    It provides the raw I/O interface on top of a socket object.
    Backported from python 3.
    """


    def __init__(self, src, dest, buf=None):

        io.RawIOBase.__init__(self)
        self._src = src
        self._dest = dest

        if not buf:
            buf = []
        self._buf = buf
        
    def readinto(self, b):
        self._checkClosed()
        self._checkReadable()
        
        buf = bytes("".join(self._buf))

        if buf and buf is not None:
            l = len(b)
            if len(self._buf) > l:
                del b[l:]

                b[0:l], buf = buf[:l], buf[l:]
                self._buf = [buf]
                return len(b)
            else:
                length = len(buf)
                del b[length:]
                b[0:length] = buf
                self._buf = []
                return len(b) 

        if _readinto is not None:
            return _readinto(self._src, b)

        while True:
            try:
                return self._src.recv_into(b)
            except socket.error as e:
                n = e.args[0]
                if n == EINTR:
                    continue
                if n in _blocking_errnos:
                    return None
                raise

    def write(self, b):
        self._checkClosed()
        self._checkWritable()

        if _write is not None:
            return _write(self._dest, b)

        try:
            return self._dest.send(b)
        except socket.error as e:
            # XXX what about EINTR?
            if e.args[0] in _blocking_errnos:
                return None
            raise

    def readable(self):
        """True if the SocketIO is open for reading.
        """
        return not self.closed

    def writable(self):
        """True if the SocketIO is open for writing.
        """
        return not self.closed

    
    def recv(self, n=None):
        return self.read(n)

    def send(self, n=None):
        return self.write(n)
