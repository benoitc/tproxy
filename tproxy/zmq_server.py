# -*- coding: utf-8 -
#
# This file is part of tproxy released under the MIT license. 
# See the NOTICE for more information.

import inspect
import io
import logging

import gevent
from gevent_zeromq import zmq

from .server import Peers
from .rewrite import RewriteIO, RewriteProxy

class ZmqRewriteIO(RewriteIO):

    """Raw I/O implementation for ZMQ sockets.

    It provides the raw I/O interface on top of a socket object.
    Backported from python 3.
    """
     
    def readinto(self, b):
        self._checkClosed()
        self._checkReadable()
        
        buf = bytes("".join(self._buf))

        if not buf:
            buf = self._src.recv()

        blen = len(b)
        buflen = len(buf)
        if buflen > blen:
            b[0:] = buf
        else:
            b[0:buflen] = b
            self._buf = []

        return buflen

class ZmqRewriteProxy(RewriteProxy):

    def run(self):
        if hasattr(self.src, 'recv_into'):
            pipe = RewriteIO(self.src, self.dest, self.buf)
        else:
            pipe = ZmqRewriteIO(self.src, self.dest, self.buf)

        spec = inspect.getargspec(self.rewrite_fun)
        try:
            if len(spec.args) > 1:
                self.rewrite_fun(pipe, self.extra)
            else:
                self.rewrite_fun(pipe)
        finally:
            pipe.close()

class ZmqServer(object):

    def __init__(self, sender_uri, receiver_uri, client, 
            extra=None, buf=None):
       
        # start to receive data
        self.context = zmq.Context()
        self.sender = self.context.socket(zmq.PUSH)
        self.sender.connect(sender_uri)
        
        self.receiver = self.context.socket(zmq.SUB)
        self.receiver.setsockopt(zmq.SUBSCRIBE, "")
        self.receiver.connect(receiver_uri)
       
        self.client = client
        self.server = client.server

        self.extra = extra
        self.buf = buf

        self.log = logging.getLogger(__name__)

    def handle(self):

        """ start to relay the response
        """
        try:
            peers = Peers([
                gevent.spawn(self.proxy_input, self.client.sock,
                    self.sender),
                gevent.spawn(self.proxy_connected, self.receiver, 
                    self.client.sock)])
            gevent.joinall(peers.greenlets)
        finally:
            pass

    def proxy_input(self, client, sender):
        """ proxy innput to the connected host
        """
        if self.server.rewrite_request is not None:
            self.rewrite(client, sender, self.server.rewrite_request,
                    extra=self.extra, buf=self.buf)
        else:
            while True:
                data = client.recv(io.DEFAULT_BUFFER_SIZE)
                if not data: 
                    print "break"
                    break
                self.log.debug("got data from input")
                sender.send(data)

    def proxy_connected(self, receiver, client):
        """ proxy the response from the connected host to the client
        """
        if self.server.rewrite_response is not None:
            self.rewrite(receiver, client, self.server.rewrite_response,
                    extra=self.extra)
        else:
            while True:
                data = receiver.recv()
                if not data:
                    break
                self.log.debug("got data from connected")
                client.sendall(data)
    

    def rewrite(self, src, dest, fun, extra=None, buf=None):
        rwproxy = ZmqRewriteProxy(src, dest, fun, timeout=self.timeout, 
                extra=extra, buf=buf)
        rwproxy.run()
