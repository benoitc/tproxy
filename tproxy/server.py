# -*- coding: utf-8 -
#
# This file is part of tproxy released under the MIT license. 
# See the NOTICE for more information.

import io
import logging

import greenlet
import gevent
from gevent.event import Event
from gevent.pool import Group, Pool

from .rewrite import RewriteIO

class InactivityTimeout(Exception):
    """ Exception raised when the configured timeout elapses without
    receiving any data from a connected server """

class Peers(Group):
    """
    Peered greenlets. If one of greenlet is killed, all are killed. 
    """
    def discard(self, greenlet):
        super(Peers, self).discard(greenlet)
        if not hasattr(self, '_killing'):
            self._killing = True
            gevent.spawn(self.kill)

class RewriteProxy(object):

    def __init__(self, src, dest, rewrite_fun, timeout=None,
            buf=None):
        self.src = src
        self.dest = dest
        self.rewrite_fun = rewrite_fun
        self.timeout = timeout
        self.buf = buf 

    def run(self):
        pipe = RewriteIO(self.src, self.dest, self.buf) 
       
        try:
            self.rewrite_fun(pipe)
        finally:
            pipe.close()

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
        try:
            peers = Peers([
                gevent.spawn(self.proxy_input, self.client.sock, self.sock),
                gevent.spawn(self.proxy_connected, self.sock, 
                    self.client.sock)])
            gevent.joinall(peers.greenlets)
        finally:
            self.sock.close

        
    def proxy_input(self, src, dest):
        """ proxy innput to the connected host
        """
        if self.server.rewrite_request is not None:
            self.rewrite(src, dest, self.server.rewrite_request,
                    buf=self.buf)
        else:
            while True:
                data = src.recv(io.DEFAULT_BUFFER_SIZE)
                if not data: 
                    break
                self.log.debug("got data from input")
                dest.sendall(data)

    def proxy_connected(self, src, dest):
        """ proxy the response from the connected host to the client
        """
        if self.server.rewrite_response is not None:
            self.rewrite(src, dest, self.server.rewrite_response)
        else:
            while True:
                with gevent.Timeout(self.timeout, InactivityTimeout): 
                    data = src.recv(io.DEFAULT_BUFFER_SIZE)
                if not data:
                    break
                self.log.debug("got data from connected")
                dest.sendall(data)

    def rewrite(self, src, dest, fun, buf=None):
        rwproxy = RewriteProxy(src, dest, fun, timeout=self.timeout, 
                buf=buf)
        rwproxy.run()
