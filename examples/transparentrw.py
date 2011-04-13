import re

def rewrite_request(req):
    while True:
        data = req.recv()
        if not data:
            break
        req.send(data)         

def rewrite_response(resp):
    while True:
        data = resp.recv()
        if not data:
            break
        resp.send(data)

def proxy(data):
    return {'remote': ('google.com', 80)}
