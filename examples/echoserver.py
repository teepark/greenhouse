#!/usr/bin/env python

import greenhouse


PORT = 9000

def connection_handler(clientsock):
    print "connection made"
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
        print "input received: %s" % received
        clientsock.sendall(received)

def main():
    print "localhost echoing server starting on port %d." % PORT
    print "shut it down with <Ctrl>-C"
    try:
        serversock = greenhouse.Socket()
        serversock.bind(("", PORT))
        serversock.listen(5)
        while 1:
            clientsock, address = serversock.accept()
            greenhouse.schedule(connection_handler, args=[clientsock])
    except KeyboardInterrupt:
        print "KeyboardInterrupt caught, closing listener socket"
        serversock.close()


if __name__ == "__main__":
    main()
