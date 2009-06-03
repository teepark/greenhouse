import collections
import errno
import functools
import socket
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from greenhouse import utils, _state, mainloop


_socket = socket.socket
_fromfd = socket.fromfd

# EBADF shouldn't be in this list, but i'm getting it for some reason
SOCKET_CLOSED = set((errno.ECONNRESET, errno.ENOTCONN, errno.ESHUTDOWN,
        errno.EBADF))

def monkeypatch():
    """replace functions in the standard library socket module
    with their non-blocking greenhouse equivalents"""
    socket.socket = Socket
    socket.fromfd = fromfd

def unmonkeypatch():
    "undo a call to monkeypatch()"
    socket.socket = _socket
    socket.fromfd = _fromfd

def fromfd(*args, **kwargs):
    return Socket(fromsock=_fromfd(*args, **kwargs))

class Socket(object):
    def __init__(self, *args, **kwargs):
        # wrap a basic socket or build our own
        self._sock = kwargs.pop('fromsock', None)
        if isinstance(self._sock, Socket):
            self._sock = self._sock._sock
        if not self._sock:
            self._sock = _socket(*args, **kwargs)

        # copy over attributes
        self.family = self._sock.family
        self.type = self._sock.type
        self.proto = self._sock.proto
        self._fileno = self._sock.fileno()

        # make the underlying socket non-blocking
        self._sock.setblocking(False)

        # create events
        self._readable = utils.Event()
        self._writable = utils.Event()

        # some more housekeeping
        self._timeout = None
        self._closed = False

        # register this socket for polling events
        if not hasattr(_state, 'poller'):
            import greenhouse.poller
        _state.poller.register(self._sock)

        # allow for lookup by fileno
        _state.sockets[self._fileno].append(self)

    def __del__(self):
        try:
            _state.poller.unregister(self._sock)
        except:
            pass

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

    def makefile(self, mode='r', bufsize=-1):
        return File(self, mode, bufsize)

    def _recv_now(self, nbytes):
        return self._sock.recv(nbytes)

    # for all the socket reading methods, we first need the readable event
    def recv(self, nbytes):
        while 1:
            try:
                return self._sock.recv(nbytes)
            except socket.error, e:
                if e[0] == errno.EWOULDBLOCK:
                    self._readable.wait()
                    continue
                if e[0] in SOCKET_CLOSED:
                    self._closed = True
                    return ''
                raise

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

    def setblocking(self, flag):
        return self._sock.setblocking(flag)

    def setsockopt(self, level, option, value):
        return self._sock.setsockopt(level, option, value)

    def shutdown(self, flag):
        return self._sock.shutdown(flag)

    def settimeout(self, timeout):
        self._timeout = timeout

class File(object):
    default_bufsize = 8192
    ENDLINE = '\r\n'

    def __init__(self, fd, mode='r', bufsize=None):
        self._fileno = isinstance(fd, int) and fd or fd.fileno()
        self._closed = False
        self._sock = self._getsock(fd)
        self.mode = mode
        self.bufsize = bufsize or self.default_bufsize
        self._readbuf = StringIO()

    def __iter__(self):
        return self

    def close(self):
        self._closed = True

    @property
    def closed(self):
        return self._closed

    def fileno(self):
        return self._sock.fileno()

    def flush(self):
        pass

    @staticmethod
    def _getsock(fd):
        if isinstance(fd, Socket):
            return fd
        return fromfd(fd, socket.AF_INET, socket.SOCK_STREAM)

    def next(self):
        buf = self._readbuf
        while 1:
            rc = buf.getvalue()
            index = buf.find(self.ENDLINE)
            if index >= 0:
                index += len(self.ENDLINE)
                buf.seek(0)
                buf.truncate()
                buf.write(rc[index:])
                return rc[:index]
            if self._sock._closed:
                buf.seek(0)
                buf.truncate()
                if rc:
                    return rc
                raise StopIteration()
            rcvd = self._sock.recv(self.bufsize)
            buf.write(rcvd)
            if not rcvd:
                if rc:
                    return rc
                raise StopIteration

    def read(self, size=None):
        buf = self._readbuf
        while 1:
            rc = buf.getvalue()
            if not rc or (size and len(rc) >= size):
                buf.seek(0)
                buf.truncate()
                if size:
                    if len(rc) > size:
                        buf.write(rc[size:])
                    return rc[:size]
                return rc
            toread = size and min(size - len(rc), self.bufsize) or self.bufsize
            rcvd = self._sock.recv(toread)
            buf.write(rcvd)
            if len(rcvd) < toread:
                rc = buf.getvalue()
                buf.seek(0)
                buf.truncate()
                return rc

    def readline(self):
        buf = self._readbuf
        while 1:
            rc = buf.getvalue()
            index = rc.find(self.ENDLINE)
            if index >= 0:
                index += len(self.ENDLINE)
                buf.seek(0)
                buf.truncate()
                buf.write(rc[index:])
                return rc[:index]
            if self._sock._closed:
                buf.seek(0)
                buf.truncate()
                return rc
            rcvd = self._sock.recv(self.bufsize)
            buf.write(rcvd)

    def readlines(self):
        return self.read().split(self.ENDLINE)

    def write(self, data):
        self._sock.sendall(data)

    def writelines(self, lines):
        self.write(self.ENDLINE.join(lines))
