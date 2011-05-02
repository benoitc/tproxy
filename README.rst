tproxy
------

tproxy is a simple TCP routing proxy (layer 7)  built on
Gevent_ that lets you configure the routine logic in Python. It's heavily
inspired from `proxy machine <https://github.com/mojombo/proxymachine>`_
but have some unique features like the pre-fork worker model borrowed to
Gunicorn_.


Instalation
-----------

tproxy requires **Python 2.x >= 2.5**. Python 3.x support is planned.

::

    $ pip install gevent
    $ pip install tproxy

To install from source::

    $ git clone git://github.com/benoitc/tproxy.git
    $ cd tproxy
    $ pip install -r requirements.txt
    $ python setup.py install


Test your installation by running the command line::

    $ tproxy examples/transparent.py

And go on http://127.0.0.1:5000 , you should see the google homepage.


Usage
-----

::

    $ tproxy -h

    Usage: tproxy [OPTIONS] script_path

    Options:
      --version                     show program's version number and exit
      -h, --help                    show this help message and exit
      --log-file=FILE               The log file to write to. [-]
      --log-level=LEVEL             The granularity of log outputs. [info]
      --log-config=FILE             The log config file to use. [None]
      -n STRING, --name=STRING      A base to use with setproctitle for process naming.
                                    [None]
      -D, --daemon                  Daemonize the Gunicorn process. [False]
      -p FILE, --pid=FILE           A filename to use for the PID file. [None]
      -u USER, --user=USER          Switch worker processes to run as this user. [501]
      -g GROUP, --group=GROUP
                                    Switch worker process to run as this group. [20]
      -m INT, --umask=INT           A bit mask for the file mode on files written by
                                    Gunicorn. [0]
      -b ADDRESS, --bind=ADDRESS    The socket to bind. [127.0.0.1:8000]
      --backlog=INT                 The maximum number of pending connections.     [2048]
      --ssl-keyfile=STRING          Ssl key file [None]
      --ssl-certfile=STRING         Ssl ca certs file. contai,s concatenated
                                    "certification [None]
      --ssl-ca-certs=STRING         Ssl ca certs file. contains concatenated
                                    "certification [None]
      --ssl-cert-reqs=INT           Specifies whether a certificate is required from the
                                    other [0]
      -w INT, --workers=INT         The number of worker process for handling requests. [1]
      --worker-connections=INT      The maximum number of simultaneous clients per worker.
                                    [1000]
      -t INT, --timeout=INT         Workers silent for more than this many seconds are
                                    killed and restarted. [30]

Signals
-------
::

    QUIT    -   Graceful shutdown. Stop accepting connections immediatly
                and wait until all connections close

    TERM    -   Fast shutdown. Stop accepting and close all conections
                after 10s.
    INT     -   Same as TERM

    HUP     -   Graceful reloading. Reload all workers with the new code
                in your routing script.
    
    USR2    -   Upgrade tproxy on the fly
    
    TTIN    -   Increase the number of worker from 1
    
    TTOU    -   Decrease the number of worker from 1


Exemple of routing script
-------------------------

::

    import re
    re_host = re.compile("Host:\s*(.*)\r\n")

    class CouchDBRouter(object):
        # look at the routing table and return a couchdb node to use
        def lookup(self, name):
            """ do something """

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

Example SOCKS4 Proxy in 18 Lines
--------------------------------

::

    import socket
    import struct

    def proxy(data):
        if len(data) < 9:
            return

        command = ord(data[1])
        ip, port = socket.inet_ntoa(data[4:8]), struct.unpack(">H", data[2:4])[0]
        idx = data.index("\0")
        userid = data[8:idx]

        if command == 1: #connect
            return dict(remote="%s:%s" % (ip, port),
                    reply="\0\x5a\0\0\0\0\0\0",
                    data=data[idx:])
        else:
            return {"close": "\0\x5b\0\0\0\0\0\0"}

Valid return values
-------------------

* { "remote:": string or tuple } - String is the host:port of the
  server that will be proxied.
* { "remote": String, "data": String} - Same as above, but
  send the given data instead.
* { "remote": String, "data": String, "reply": String} - Same as above,
  but reply with given data back to the client 
* None  - Do nothing.
* { "close": True } - Close the connection.
* { "close": String } - Close the connection after sending
  the String.

To handle ssl for remote connection you can add these optionals
arguments:

- ssl: True or False, if you want to connect with ssl
- ssl_args: dict, optionals ssl arguments. Read the `ssl documentation
  <http://docs.python.org/library/ssl.html?highlight=ssl.wrap_socket#ssl.wrap_socket>`_ for more informations about them. 

Handle errors
-------------

You can easily handling error by adding a **proxy_error** function in
your script::

    def proxy_error(client, e):
        pass

This function get the ClientConnection instance (current connection) as
first arguments and the error exception in second argument.

Rewrite requests & responses
----------------------------

Main goal of tproxy is to allows you to route transparently tcp to your
applications. But some case you want to do more. For example you need in
HTTP 1.1 to change the Host header to make sure remote HTTP server will
know what to do if uses virtual hosting.

To do that, add a **rewrite_request** function in your function to
simply rewrite clienrt request and **rewrite_response** to rewrite the
remote response. Both functions take a tproxy.rewrite.RewriteIO instance
which is based on io.RawIOBase class.

See the `httprewrite.py <https://github.com/benoitc/tproxy/blob/master/examples/httprewrite.py>`_ example for an example of HTTP rewrite.


Copyright
---------
2011 (c) Benoît Chesneau <benoitc@e-engura.org>


.. _Gevent: http://gevent.org
.. _Gunicorn: http://gunicorn.org
