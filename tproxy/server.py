# -*- coding: utf-8 -
#
# This file is part of tproxy released under the MIT license. 
# See the NOTICE for more information.

import logging

import gevent

class ServerConnection(object):

    def __init__(self, sock, client, timeout=None):
        self.sock = sock
        self.timeout = timeout
        self.client = client
        self.log = logging.getLogger(__name__)
        
    def handle(self):
        jobs = [
            gevent.spawn(self.proxy, self.client.sock, self.sock,
                "client_side"),
            gevent.spawn(self.proxy, self.sock, self.client.sock,
                "server_side"),
            ]
        gevent.joinall(jobs)

    def proxy(self, src, dest, side=None):
        while True:
            data = src.recv(8192)
            if not data:
                break
            self.log.debug("%s got data" % side)

            dest.sendall(data)







