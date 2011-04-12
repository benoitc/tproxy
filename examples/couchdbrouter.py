import re
re_host = re.compile("Host:\s*(.*)\r\n")

class CouchDBRouter(object):
    # look at the routing table and return a couchdb node to use
    def lookup(self, name):
        """ do something """
        return ("127.0.0.1",15984)
router = CouchDBRouter()

# Perform content-aware routing based on the stream data. Here, the
# Host header information from the HTTP protocol is parsed to find the 
# username and a lookup routine is run on the name to find the correct
# couchdb node. If no match can be made yet, do nothing with the
# connection. (make your own couchone server...)

def proxy(data):
    matches = re_host.findall(data)
    if matches:
        host = router.lookup(matches.pop()) 
        return {"remote": host}
    return None
