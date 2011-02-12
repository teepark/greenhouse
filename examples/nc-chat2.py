#!/usr/bin/env python

import greenhouse
SocketServer = greenhouse.patched("SocketServer")

import traceback
greenhouse.add_exception_handler(traceback.print_exception)

PORT = 9000

connections = {}


class NCChatHandler(SocketServer.StreamRequestHandler):
    def handle(self):
        self.connection.sendall("enter your name up to 20 characters\r\n")

        name = self.rfile.readline().rstrip()
        if len(name) > 20:
            self.connection.sendall("name too long!\r\n")
            return

        if name in connections:
            self.connection.sendall("already have a '%s'\r\n" % name)
            return

        connections[name] = self

        greenhouse.schedule(self._broadcast, args=(
            "** %s has entered the room" % name,
            self))

        for line in self.rfile:
            if not line:
                del connections[name]
                break

            greenhouse.schedule(self._broadcast, args=(
                "%s: %s" % (name, line.rstrip()),))

        greenhouse.schedule(self._broadcast, args=(
            "** %s has left the room" % name,
            self))

    def _broadcast(self, message, skip=None):
        for conn in connections.itervalues():
            if (skip and conn is skip) or conn.connection._closed:
                continue

            conn.connection.sendall("%s\r\n" % message)


if __name__ == '__main__':
    server = SocketServer.ThreadingTCPServer(("", PORT), NCChatHandler)
    server.allow_reuse_address = True
    print "localhost nc chat server starting on port %d." % PORT
    print "shut it down with <Ctrl>-C"
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print "KeyboardInterrupt caught, closing connections"
        for conn in connections.itervalues():
            conn.connection.close()
