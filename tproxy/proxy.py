# -*- coding: utf-8 -
#
# This file is part of tproxy released under the MIT license. 
# See the NOTICE for more information.

import errno
import logging
import os
import signal
import sys
import time

import gevent
from gevent.server import StreamServer
from gevent import socket

# we patch all
from gevent import monkey
monkey.noisy = False
monkey.patch_all()


from .client import ClientConnection
from . import util

log = logging.getLogger(__name__)


class ProxyServer(StreamServer):

    def __init__(self, listener, script, name=None, backlog=None, 
            spawn='default', **sslargs):
        StreamServer.__init__(self, listener, backlog=backlog,
                spawn=spawn, **sslargs)
        self.name = name
        self.script = script
        self.nb_connections = 0
        self.route = None
        self.rewrite_request = None
        self.rewrite_response = None

    def handle_quit(self, *args):
        """Graceful shutdown. Stop accepting connections immediately and
        wait as long as necessary for all connections to close.
        """
        gevent.spawn(self.stop)

    def handle_exit(self, *args):
        """ Fast shutdown.Stop accepting connection immediatly and wait
        up to 10 seconds for connections to close before forcing the
        termination
        """
        gevent.spawn(self.stop, 10.0)

    def handle_winch(self, *args):
        # Ignore SIGWINCH in worker. Fixes a crash on OpenBSD.
        return

    def pre_start(self):
        """ create socket if needed and bind SIGKILL, SIGINT & SIGTERM
        signals
        """
        # setup the socket
        if not hasattr(self, 'socket'):
            self.socket = tcp_listener(self.address, self.backlog)
            self.address = self.socket.getsockname()
        self._stopped_event.clear()

         # make SSL work:
        if self.ssl_enabled:
            self._handle = self.wrap_socket_and_handle
        else:
            self._handle = self.handle

        # handle signals
        signal.signal(signal.SIGQUIT, self.handle_quit)
        signal.signal(signal.SIGTERM, self.handle_exit)
        signal.signal(signal.SIGINT, self.handle_exit)
        signal.signal(signal.SIGWINCH, self.handle_winch)

    def refresh_name(self):
        title = "worker"
        if self.name is not None:
            title += " [%s]"
        title = "%s - handling %s connections" % (title, self.nb_connections)
        util._setproctitle(title)

    def stop_accepting(self):
        title = "worker"
        if self.name is not None:
            title += " [%s]"
        title = "%s - stop accepting" % title
        util._setproctitle(title)
        super(ProxyServer, self).stop_accepting()

    def start_accepting(self):
        self.refresh_name() 
        super(ProxyServer, self).start_accepting()

    def serve_forever(self):
        if hasattr(self.script, "load"):
            self.route = self.script.load()
        else:
            self.route = self.script
       
        try: 
            self.rewrite_request = self.route.rewrite_request
        except AttributeError:
            pass 
       
        try:
            self.rewrite_response =  self.route.rewrite_response
        except AttributeError:
            pass 

        super(ProxyServer, self).serve_forever()

    def handle(self, socket, address):
        """ handle the connection """
        conn = ClientConnection(socket, address, self)
        conn.handle()

    def wrap_socket_and_handle(self, client_socket, address):
        # used in case of ssl sockets
        ssl_socket = self.wrap_socket(client_socket, **self.ssl_args)
        return self.handle(ssl_socket, address)

def tcp_listener(address, backlog=None):
    backlog = backlog or 128

    if util.is_ipv6(address[0]):
        family = socket.AF_INET6
    else:
        family = socket.AF_INET

    bound = False
    if 'TPROXY_FD' in os.environ:
        fd = int(os.environ.pop('TPROXY_FD'))
        try:
            sock = socket.fromfd(fd, family, socket.SOCK_STREAM)
        except socket.error, e:
            if e[0] == errno.ENOTCONN:
                log.error("TPROXY_FD should refer to an open socket.")
            else:
                raise
        bound = True
    else:
        sock = socket.socket(family, socket.SOCK_STREAM)

    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    for i in range(5):
        try:
            if not bound:
                sock.bind(address) 
            sock.setblocking(0)
            sock.listen(backlog)
            return sock
        except socket.error, e:
            if e[0] == errno.EADDRINUSE:
                log.error("Connection in use: %s" % str(address))
            if e[0] == errno.EADDRNOTAVAIL:
                log.error("Invalid address: %s" % str(address))
                sys.exit(1)
            if i < 5:
                log.error("Retrying in 1 second. %s" % str(e))
                time.sleep(1)
