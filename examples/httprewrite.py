import re
from http_parser.http import HttpStream, NoMoreData
from http_parser.reader import SocketReader
import socket

def rewrite_headers(parser, values=None):
    try:
        headers = parser.headers()
        if isinstance(values, dict):
            headers.update(values)

        httpver = "HTTP/%s" % ".".join(map(str, 
                    parser.version()))

        new_headers = ["%s %s %s\r\n" % (parser.method(), parser.url(), 
            httpver)]

        new_headers.extend(["%s: %s\r\n" % (k, str(v)) for k, v in \
                headers.items()])

        return "".join(new_headers) + "\r\n"
    except NoMoreData:
        return


def rewrite_request(req):
    try: 
        while True:
            parser = HttpStream(req)
                
            new_headers = rewrite_headers(parser, {'Host': 'gunicorn.org'})
            if new_headers is None:
                break
            req.send(new_headers)
            body = parser.body_file()
            while True:
                data = body.read(8192)
                if not data:
                    break
                req.send(data)
            if not parser.should_keep_alive():
                print "don't keep alive"
                break
    except socket.error:
        pass


def rewrite_response(resp):
    while True:
        parser = HttpStream(resp)
        # we aren't doing anything here
        for data in parser:
            resp.send(data)
 
        if not parser.should_keep_alive():
            # close the connection.
            break

def proxy(data):
    return {'remote': ('gunicorn.org', 80)}
