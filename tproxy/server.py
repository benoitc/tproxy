# -*- coding: utf-8 -
#
# This file is part of tproxy released under the MIT license. 
# See the NOTICE for more information.

import logging

import gevent

class InactivityTimeout(Exception):
    """ Exception raised when the configured timeout elapses without
    receiving any data from a connected server """

class ServerConnection(object):

    def __init__(self, sock, client, timeout=None):
        self.sock = sock
        self.timeout = timeout
        self.client = client
        self.log = logging.getLogger(__name__)
        
    def handle(self):
        jobs = [
            gevent.spawn(self.proxy_input, self.client.sock, self.sock),
            gevent.spawn(self.proxy_connected, self.sock, self.client.sock),
            ]
        gevent.joinall(jobs)


    def proxy_input(self, src, dest):
        while True:
            data = src.recv(8192)
            if not data:
                break
            self.log.debug("got data from input")
            dest.sendall(data)



    def proxy_connected(self, src, dest):
        while True:
            with gevent.Timeout(self.timeout, InactivityTimeout): 
                data = src.recv(8192)
            if not data:
                break
            self.log.debug("got data from connected")
            dest.sendall(data)




