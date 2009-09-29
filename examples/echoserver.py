#!/usr/bin/env python

import socket

import greenhouse


PORT = 9000

def connection_handler(clientsock, address):
    print "connection made from %s:%s" % address
    clientfile = clientsock.makefile()
    while 1:
        if clientsock._closed:
            print "connection was closed"
            break

        input = received = clientsock.recv(8192)
        if not input:
            print "connection was closed"
            break

        while len(input) == 8192:
            input = clientsock.recv(8192)
            received += input
        print "input received: %s" % received.rstrip('\r\n')
        clientsock.sendall(received)

def main():
    print "localhost echoing server starting on port %d." % PORT
    print "shut it down with <Ctrl>-C"
    try:
        serversock = greenhouse.Socket()
        serversock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        serversock.bind(("", PORT))
        serversock.listen(5)
        while 1:
            clientsock, address = serversock.accept()
            greenhouse.schedule(connection_handler, args=[clientsock, address])
    except KeyboardInterrupt:
        print "KeyboardInterrupt caught, closing listener socket"
        serversock.close()


if __name__ == "__main__":
    main()
