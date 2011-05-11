# -*- coding: utf-8 -
#
# This file is part of tproxy released under the MIT license. 
# See the NOTICE for more information.

import io
import logging

from .rewrite import RewriteProxy

class Route(object):
    """ toute object to handle real proxy """

    def __init__(self, script):
        if hasattr(script, "load"):
            self.script = script.load()
        else:
            self.script = script

        self.empty_buf = True
        if hasattr(self.script, 'rewrite_request'):
            self.proxy_input = self.rewrite_request
            self.empty_buf = False
        else:
            self.proxy_input = self.proxy_io

        if hasattr(self.script, 'rewrite_response'):
            self.proxy_connected = self.rewrite_response
        else:
            self.proxy_connected = self.proxy_io

        self.log = logging.getLogger(__name__)

    def proxy(self, data):
        return self.script.proxy(data)

    def proxy_io(self, src, dest, buf=None, extra=None):
        while True:
            data = src.recv(io.DEFAULT_BUFFER_SIZE)
            if not data: 
                break
            self.log.debug("got data from input")
            dest.sendall(data)

    def rewrite(self, src, dest, fun, buf=None, extra=None):
        rwproxy = RewriteProxy(src, dest, fun, extra=extra, buf=buf)
        rwproxy.run()

    def rewrite_request(self, src, dest, buf=None, extra=None):
        self.rewrite(src, dest, self.script.rewrite_request, buf=buf,
                extra=extra)
        
    def rewrite_response(self, src, dest, extra=None):
        self.rewrite(src, dest, self.script.rewrite_response, 
                extra=extra)
