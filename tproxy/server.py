# -*- coding: utf-8 -
#
# This file is part of tproxy released under the MIT license. 
# See the NOTICE for more information.

import logging

import greenlet
import gevent
from gevent.event import Event
from gevent.pool import Group, Pool


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

class ServerConnection(object):

    def __init__(self, sock, client, timeout=None, extra=None,
            buf=None):
        self.sock = sock
        self.timeout = timeout
        self.client = client
        self.extra = extra
        self.buf = buf

        self.route = client.route

        self.log = logging.getLogger(__name__)
        self._stopped_event = Event()
        
    def handle(self):
        """ start to relay the response
        """
        try:
            peers = Peers([
                gevent.spawn(self.route.proxy_input, self.client.sock,
                    self.sock, self.buf, self.extra),
                gevent.spawn(self.route.proxy_connected, self.sock, 
                    self.client.sock, self.extra)])
            gevent.joinall(peers.greenlets)
        finally:
            self.sock.close()

        
    def proxy_input(self, src, dest, buf, extra):
        """ proxy innput to the connected host
        """
        self.route.proxy_input(src, dest, buf=buf, extra=extra) 

    def proxy_connected(self, src, dest, extra):
        """ proxy the response from the connected host to the client
        """
        self.route.proxy_connected(src, dest, extra=extra) 
