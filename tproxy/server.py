# -*- coding: utf-8 -
#
# This file is part of tproxy released under the MIT license. 
# See the NOTICE for more information.

import logging

import gevent
from gevent.event import Event
from gevent.pool import Pool
from gevent.queue import Queue

CHUNK_SIZE = 8192

class InactivityTimeout(Exception):
    """ Exception raised when the configured timeout elapses without
    receiving any data from a connected server """


class RewriteDevice(object):
    
    def __init__(self, qin, qout):
        self._qin = qin
        self._qout = qout
        self._buffer = ""
        self.eof = False

    def __iter__(self):
        return self

    def next(self):
        data = self.recv()
        if not data:
            raise StopIteration
        return data

    def recv(self, size=-1):
        if self.eof:
            return ""

        if size < 0:
            if len(self._buffer):
                return self._buffer
            return self._qin.get()
        
        buf = self._buffer
        while len(buf) < size:
            chunk = self._qin.get()
            if not chunk:
                break
            buf += chunk

            # we queued less, we don't need to continue
            if len(chunk) < CHUNK_SIZE:
                break

        n = min(size, len(buf))
        data, self._buffer = buf[:n], buf[n:]
        return data

    def send(self, data):
        n = len(data)
        self._qout.put(data)
        return n

    def close(self):
        raise StopIteration

class RewriteProxy(object):

    def __init__(self, src, dest, rewrite_fun, timeout=None,
            buf=None):
        self.src = src
        self.dest = dest
        self.rewrite_fun = rewrite_fun
        self.timeout = timeout
        self.qin = Queue()
        self.qout = Queue()

        if buf and buf is not None:
            for chunk in buf:
                self.qin.put(chunk)

    def run(self):
        pool = Pool(
                gevent.spawn(self._fetch_input),
                gevent.spawn(self._send_output))

        device = RewriteDevice(self.qin, self.qout)
        try:
            self.rewrite_fun(device)
        except:
            pool.join(timeout=self.timeout)
            pool.kill(block=True, timeout=1)
            raise

    def _fetch_input(self):
        while True:
            with gevent.Timeout(self.timeout, InactivityTimeout): 
                data = self.src.recv(CHUNK_SIZE)
            self.qin.put(data)
            if not data:
                break
                    
    def _send_output(self):
        while True:
            data = self.qout.get()
            if not data:
                break
            self.dest.sendall(data)


class ServerConnection(object):

    def __init__(self, sock, client, timeout=None, buf=None):
        self.sock = sock
        self.timeout = timeout
        self.client = client
        self.server = client.server
        self.buf = buf

        self.log = logging.getLogger(__name__)
        self._stopped_event = Event()
        
    def handle(self):
        """ start to relay the response
        """

        self.pool = Pool(
            gevent.spawn(self.proxy_input, self.client.sock, self.sock),
            gevent.spawn(self.proxy_connected, self.sock, self.client.sock),
        )

        try:
            self._stopped_event.wait()
        except:
            self.pool.join(timeout=self.timeout)
            self.pool.kill(block=True, timeout=1)
            raise

    def proxy_input(self, src, dest):
        """ proxy innput to the connected host
        """
        if self.server.rewrite_request is not None:
            self.rewrite(src, dest, self.server.rewrite_request,
                    buf=self.buf) 
        else:
            while True:
                data = src.recv(CHUNK_SIZE)
                if not data: 
                    break
                self.log.debug("got data from input")
                dest.sendall(data)
        self._stopped_event.set()

    def proxy_connected(self, src, dest):
        """ proxy the response from the connected host to the client
        """
        if self.server.rewrite_response is not None:
            self.rewrite(src, dest, self.server.rewrite_response)
        else:
            while True:
                with gevent.Timeout(self.timeout, InactivityTimeout): 
                    data = src.recv(CHUNK_SIZE)
                if not data:
                    break
                self.log.debug("got data from connected")
                dest.sendall(data)

        self._stopped_event.set()

    def rewrite(self, src, dest, fun, buf=None):
        rwproxy = RewriteProxy(src, dest, fun, timeout=self.timeout, 
                buf=buf)
        rwproxy.run()
