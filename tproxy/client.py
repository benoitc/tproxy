# -*- coding: utf-8 -
#
# This file is part of tproxy released under the MIT license. 
# See the NOTICE for more information.

import logging
import ssl

import gevent
from gevent import coros
from gevent import socket
import greenlet

from .server import ServerConnection, InactivityTimeout
from .util import parse_address, is_ipv6

log = logging.getLogger(__name__)

class ConnectionError(Exception):
    """ Exception raised when a connection is either rejected or a
    connection timeout occurs """

class ClientConnection(object):

    def __init__(self, sock, addr, server):
        self.sock = sock
        self.addr = addr
        self.server = server

        self.route = server.route
        self.buf = []
        self.remote = None
        self.connected = False
        self._lock = coros.Semaphore()

    def handle(self):
        with self._lock:
            self.server.nb_connections +=1
            self.server.refresh_name()

        try:
            while not self.connected:
                data = self.sock.recv(8192)
                if not data:
                    break
                self.buf.append(data)
                if self.remote is None:
                    try:
                        self.do_proxy()
                    except StopIteration:
                        break
        except ConnectionError, e:
            log.error("Error while connecting: [%s]" % str(e))
            self.handle_error(e)
        except InactivityTimeout, e:
            log.warn("inactivity timeout")
            self.handle_error(e)
        except socket.error, e:
            log.error("socket.error: [%s]" % str(e))
            self.handle_error(e)
        except greenlet.GreenletExit:
            pass
        except KeyboardInterrupt:
            pass
        except Exception, e:
            log.error("unknown error %s" % str(e))
        finally:
            if self.remote is not None:
                log.debug("Close connection to %s:%s" % self.remote)

            with self._lock:
                self.server.nb_connections -=1
                self.server.refresh_name()
            _closesocket(self.sock)

    def handle_error(self, e):
        if hasattr(self.route, 'proxy_error'):
            self.route.proxy_error(self, e)

    def do_proxy(self):
        commands = self.route.proxy("".join(self.buf))
        if commands is None: # do nothing
            return 

        if not isinstance(commands, dict):
            raise StopIteration
        
        if 'remote' in commands:
            remote = parse_address(commands['remote'])
            if 'data' in commands:
                self.buf = [commands['data']]
            if 'reply' in commands:
                self.send_data(self.sock, commands['reply'])
            
            is_ssl = commands.get('ssl', False)
            ssl_args = commands.get('ssl_args', {})
            extra = commands.get('extra')
            connect_timeout = commands.get('connect_timeout')
            inactivity_timeout = commands.get('inactivity_timeout')
            self.connect_to_resource(remote, is_ssl=is_ssl, connect_timeout=connect_timeout,
                    inactivity_timeout=inactivity_timeout, extra=extra,
                    **ssl_args)

        elif 'close' in commands:
            if isinstance(commands['close'], basestring): 
                self.send_data(self.sock, commands['close'])
            raise StopIteration()
        else:
            raise StopIteration()

    def send_data(self, sock, data):
        if hasattr(data, 'read'):
            try:
                data.seek(0)
            except (ValueError, IOError):
                pass
            
            while True:
                chunk = data.readline()
                if not chunk:
                    break
                sock.sendall(chunk)    
        elif isinstance(data, basestring):
           sock.sendall(data)
        else:
            for chunk in data:
                sock.sendall(chunk)

    def connect_to_resource(self, addr, is_ssl=False, connect_timeout=None,
            inactivity_timeout=None, extra=None, **ssl_args):

        with gevent.Timeout(connect_timeout, ConnectionError):
            try:
                if is_ipv6(addr[0]):
                    sock = socket.socket(socket.AF_INET6, 
                            socket.SOCK_STREAM)
                else:
                    sock = socket.socket(socket.AF_INET, 
                            socket.SOCK_STREAM)

                if is_ssl:
                    sock = ssl.wrap_socket(sock, **ssl_args)
                sock.connect(addr)
            except socket.error, e:
                raise ConnectionError(
                        "socket error while connectinng: [%s]" % str(e))

        self.remote = addr
        self.connected = True
        log.debug("Successful connection to %s:%s" % addr)

        if self.buf and not self.server.rewrite_request:
            self.send_data(sock, self.buf)
            self.buf = []

        server = ServerConnection(sock, self, 
                timeout=inactivity_timeout, extra=extra, buf=self.buf)
        server.handle()

def _closesocket(sock):
    try:
        sock._sock.close()
        sock.close()
    except socket.error:
        pass
