import io
import re

def rewrite_request(req):
    while True:
        data = req.read(io.DEFAULT_BUFFER_SIZE)
        if not data:
            break
        req.write(data) 

def rewrite_response(resp):
    while True:
        data = resp.read(io.DEFAULT_BUFFER_SIZE)
        if not data:
            break
        resp.write(data)

def proxy(data):
    return {'remote': ('google.com', 80)}
