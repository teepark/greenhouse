import collections
import errno
import socket

from greenhouse import utils, globals


_socket = socket.socket # in case we want to monkey-patch

class GreenSocket(object):
    def __init__(self, *args, **kwargs):
        # wrap a basic socket or build our own
        self._sock = kwargs.pop('fromsock', None)
        if isinstance(self._sock, GreenSocket):
            self._sock = self._sock._sock
        if not self._sock:
            self._sock = _socket(*args, **kwargs)

        # copy over attributes
        self.family = self._sock.family
        self.type = self._sock.type
        self.proto = self._sock.proto
        self._fileno = self._sock.fileno()

        # share certain properties by filenumber, not socket instance
        socksforfd = globals.sockets[self._fileno]
        if socksforfd:
            copyfrom = socksforfd[0]
            self._readable = copyfrom._readable
            self._writable = copyfrom._writable
            self._timeout = copyfrom._timeout
            self._closed = copyfrom._closed
        else:
            # make the underlying socket non-blocking
            self._sock.setblocking(False)

            # create events
            self._readable = utils.Event()
            self._writable = utils.Event()

            # some more housekeeping
            self._timeout = None
            self._closed = False

            # register this socket for polling events
            if not hasattr(globals, 'poller'):
                import greenhouse.poller
            globals.poller.register(self._sock)

        # for looking up by file number
        socksforfd.append(self)

    def __del__(self):
        try:
            globals.poller.unregister(self._sock)
        except:
            pass

    # for all the socket reading methods, we first need the readable event
    def recv(self, nbytes):
        self._readable.wait()
        return self._sock.recv(nbytes)

    def recv_into(self, buffer, nbytes):
        self._readable.wait()
        return self._sock.recv_into(buffer, nbytes)

    def recvfrom(self, nbytes):
        self._readable.wait()
        return self._sock.recvfrom(nbytes)

    def recvfrom_into(self, buffer, nbytes):
        self._readable.wait()
        return self._sock.recvfrom_into(buffer, nbytes)

    # don't expect write calls to block, but maybe throw exceptions
    def send(self, data):
        try:
            return self._sock.send(data)
        except socket.error, err:
            if err[0] in (errno.EWOULDBLOCK, errno.ENOTCONN):
                return 0
            raise

    def sendall(self, data):
        sent = self.send(data)
        while sent < len(data):
            self._writable.wait()
            sent += self.send(data[sent:])

    def sendto(self, *args):
        try:
            return self._sock.sendto(*args)
        except socket.error, err:
            if err[0] in (errno.EWOULDBLOCK, errno.ENOTCONN):
                return 0
            raise

    def accept(self):
        while 1:
            try:
                client, addr = self._sock.accept()
            except socket.error, err:
                if err[0] == errno.EWOULDBLOCK:
                    pass
                raise
            else:
                return type(self)(fromsock=client), addr
            self._readable.wait()

    def bind(self, *args, **kwargs):
        return self._sock.bind(*args, **kwargs)

    def close(self):
        if self._closed:
            return
        del globals.sockets[self._fileno]
        for sock in globals.sockets[self._fileno]:
            sock._closed = True
        return self._sock.close()

    def connect(self, address):
        while True:
            err = self._sock.connect_ex(address)
            if err in (errno.EINPROGRESS, errno.EALREADY, errno.EWOULDBLOCK):
                self._writable.wait()
                continue
            if err not in (0, errno.EISCONN):
                raise socket.error(err, errno.errorcode[err])
            return

    def connect_ex(self, address):
        return self._sock.connect_ex(address)

    def dup(self):
        return type(self)(fromsock=self._sock.dup())

    def fileno(self):
        return self._fileno

    def getpeername(self):
        return self._sock.getpeername()

    def getsockname(self):
        return self._sock.getsockname()

    def getsockopt(self, *args):
        return self._sock.getsockopt(*args)

    def gettimeout(self):
        return self._timeout

    def listen(self, backlog):
        return self._sock.listen(backlog)

    def makefile(self):
        return self._sock.makefile()

    def setblocking(self, flag):
        return self._sock.setblocking(flag)

    def setsockopt(self, level, option, value):
        return self._sock.setsockopt(level, option, value)

    def shutdown(self, flag):
        return self._sock.shutdown(flag)

    def settimeout(self, timeout):
        for sock in globals.sockets[self._fileno]:
            sock._timeout = timeout

def monkeypatch():
    socket.socket = GreenSocket
