#!/usr/bin/env python

import socket

import greenhouse


PORT = 9000
CONNECTED = {}

def start():
    print "localhost nc chat server starting on port %d." % PORT
    print "shut it down with <Ctrl>-C"

    try:
        serversock = greenhouse.Socket()
        serversock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        serversock.bind(("", PORT))
        serversock.listen(5)

        while 1:
            clientsock, address = serversock.accept()
            greenhouse.schedule(connection_handler, args=(clientsock,))

    except KeyboardInterrupt:
        print "KeyboardInterrupt caught, closing connections"
        serversock.close()
        for sock in CONNECTED.values():
            sock.close()

def broadcast(msg, skip=None):
    for recip in CONNECTED:
        sock = CONNECTED.get(recip)
        if sock and not sock._closed and skip != recip:
            sock.sendall(msg)

def connection_handler(clientsock):
    clientsock.sendall("enter your name up to 20 characters\r\n")
    name = clientsock.recv(8192).rstrip("\r\n")

    if len(name) > 20:
        clientsock.close()
        return

    CONNECTED[name] = clientsock

    greenhouse.schedule(broadcast, args=("*** %s has entered\n" % name, name))

    sockfile = clientsock.makefile("r")
    while 1:
        line = sockfile.readline()
        if not line:
            CONNECTED.pop(name)
            break

        greenhouse.schedule(broadcast, args=(
            "%s: %s\n" % (name, line.rstrip("\r\n")), name))

    broadcast("*** %s has left the building\n" % name)



if __name__ == "__main__":
    start()
