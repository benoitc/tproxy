# -*- coding: utf-8 -
#
# This file is part of tproxy released under the MIT license. 
# See the NOTICE for more information.


""" simple proxy that can be used behind a browser. """

import io
import urlparse
import socket

from http_parser.http import HttpStream, NoMoreData, ParserError
from http_parser.parser import HttpParser
from tproxy.util import parse_address

def get_host(addr, is_ssl=False):
    """ return a correct Host header """
    host = addr[0]
    if addr[1] != (is_ssl and 443 or 80):
        host = "%s:%s" % (host, addr[1])
    return host


def write_chunk(to, data):
    """ send a chunk encoded """
    chunk = "".join(("%X\r\n" % len(data), data, "\r\n"))
    to.writeall(chunk)

def write(to, data):
    to.writeall(data)

def send_body(to, body, chunked=False):
    if chunked:
        _write = write_chunk
    else:
        _write = write

    while True:
        data = body.read(io.DEFAULT_BUFFER_SIZE)
        if not data:
            break
        _write(to, data)

    if chunked:
        _write(to, "")

def rewrite_request(req):
    try:
        while True:
            parser = HttpStream(req)
            headers = parser.headers()

            parsed_url = urlparse.urlparse(parser.url())

            is_ssl = parsed_url.scheme == "https"

            host = get_host(parse_address(parsed_url.netloc, 80),
                is_ssl=is_ssl)
            headers['Host'] = host
            headers['Connection'] = 'close'

            if 'Proxy-Connection' in headers:
                del headers['Proxy-Connection']


            location = urlparse.urlunparse(('', '', parsed_url.path,
                parsed_url.params, parsed_url.query, parsed_url.fragment))

            httpver = "HTTP/%s" % ".".join(map(str, 
                        parser.version()))

            new_headers = ["%s %s %s\r\n" % (parser.method(), location, 
                httpver)]

            new_headers.extend(["%s: %s\r\n" % (hname, hvalue) \
                    for hname, hvalue in headers.items()])

            req.writeall(bytes("".join(new_headers) + "\r\n"))
            body = parser.body_file()
            send_body(req, body, parser.is_chunked())

    except (socket.error, NoMoreData, ParserError):
            pass
    
def proxy(data):
    recved = len(data)

    parser = HttpParser()
    parsed = parser.execute(data, recved)
    if parsed != recved:
        return  { 'close':'HTTP/1.0 502 Gateway Error\r\n\r\nError parsing request'}

    if not parser.get_url():
        return

    parsed_url = urlparse.urlparse(parser.get_url())

    is_ssl = parsed_url.scheme == "https"
    remote = parse_address(parsed_url.netloc, 80)

    return {"remote": remote, 
            "ssl": is_ssl}
