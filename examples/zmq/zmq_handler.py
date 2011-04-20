import gevent
from gevent_zeromq import zmq


import socket

# server
context = zmq.Context()

receiver = context.socket(zmq.PULL)
receiver.bind("tcp://*:5558")


controller = context.socket(zmq.PUB)
controller.bind("tcp://*:5559")


def serve(receiver, controller):
    while True:
        message = receiver.recv()
        print "Received request: ", message
        controller.send(message)
gserver = gevent.spawn(serve, receiver, controller)


gserver.join()
