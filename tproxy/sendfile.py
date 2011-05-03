# -*- coding: utf-8 -
#
# This file is part of tproxy released under the MIT license. 
# See the NOTICE for more information.

import errno
import io
import os
try:
    from os import sendfile
except ImportError:
    try:
        from _sendfile import sendfile
    except ImportError:
        def sendfile(fdout, fdin, offset, nbytes):
            fsize = os.fstat(fdin).st_size

            # max to send
            length = min(fsize-offset, nbytes)

            with os.fdopen(fdin) as fin:          
                fin.seek(offset)

                while length > 0:
                    l = min(length, io.DEFAULT_BUFFER_SIZE)
                    os.write(fdout, fin.read(l))
                    length = length - l

            return length

from gevent.socket import wait_write


def async_sendfile(fdout, fdin, offset, nbytes):
    total_sent = 0
    while total_sent < nbytes:
        try:
            sent = sendfile(fdout, fdin, offset + total_sent, 
                    nbytes - total_sent)
            total_sent += sent
        except OSError, e:
            if e.args[0] == errno.EAGAIN:
                wait_write(fdout)
            else:
                raise
    return total_sent
