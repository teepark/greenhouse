from __future__ import with_statement

import contextlib
import errno
import socket
import weakref

import greenhouse
from greenhouse.io.files import FileBase
from greenhouse.scheduler import state


_socket = socket.socket
_socketpair = socket.socketpair
_fromfd = socket.fromfd

SOCKET_CLOSED = set((errno.ECONNRESET, errno.ENOTCONN, errno.ESHUTDOWN))

_more_sock_methods = ("accept", "makefile")


class Socket(object):
    __slots__ = ["_sock", "__weakref__"]

    def __getattr__(self, name):
        if name in self._socket_methods:
            return getattr(self._sock, name)
        raise AttributeError("'Socket' object has not attribute '%s'" % name)

    def __init__(self, *args, **kwargs):
        self._sock = _InnerSocket(*args, **kwargs)

    def close(self):
        self._sock = socket._closedsocket()

    def dup(self):
        copy = object.__new__(type(self))
        copy._sock = self._sock.dup()
        return copy

    _socket_methods = set(socket._delegate_methods + socket._socketmethods +
            _more_sock_methods)


def socket_fromfd(fd, family, type_, *args):
    raw_sock = socket.fromfd(fd, family, type_, *args)
    return Socket(fromsock=raw_sock)


class _InnerSocket(object):
    def __init__(self, *args, **kwargs):
        # wrap a basic socket or build our own
        sock = kwargs.pop('fromsock', None) or _socket(*args, **kwargs)
        if hasattr(sock, "_sock"):
            self._sock = sock._sock
        else:
            self._sock = sock

        # copy over attributes
        self.family = self._sock.family
        self.type = self._sock.type
        self.proto = self._sock.proto
        self._fileno = self._sock.fileno()

        # some more housekeeping
        self._timeout = sock.gettimeout()
        self._closed = False

        # make the underlying socket non-blocking
        self._sock.setblocking(False)
        self._blocking = True

        # create events
        self._readable = greenhouse.Event()
        self._writable = greenhouse.Event()

        # allow for lookup by fileno
        state.descriptormap[self._fileno].append(weakref.ref(self))

    @contextlib.contextmanager
    def _registered(self, events=None):
        poller = state.poller
        mask = None
        if events:
            mask = 0
            if 'r' in events:
                mask |= poller.INMASK
            if 'w' in events:
                mask |= poller.OUTMASK
            if 'e' in events:
                mask |= poller.ERRMASK
        try:
            counter = poller.register(self, mask)
        except EnvironmentError, error:
            if error.args and error.args[0] in errno.errorcode:
                raise socket.error(*error.args)
            raise

        try:
            yield
        finally:
            try:
                poller.unregister(self, counter)
            except EnvironmentError, error:
                if error.args and error.args[0] in errno.errorcode:
                    raise socket.error(*error.args)
                raise

    def accept(self):
        with self._registered('re'):
            while 1:
                try:
                    client, addr = self._sock.accept()
                except socket.error, err:
                    if self._blocking and err[0] in (
                            errno.EAGAIN, errno.EWOULDBLOCK):
                        if self._readable.wait(self.gettimeout()):
                            raise socket.timeout("timed out")
                        continue
                    else:
                        raise
                return type(self)(fromsock=client), addr

    def bind(self, *args, **kwargs):
        return self._sock.bind(*args, **kwargs)

    def close(self):
        self._closed = True
        self._sock.close()

    def connect(self, address):
        with self._registered('we'):
            while True:
                err = self.connect_ex(address)
                if self._blocking and err in (
                        errno.EINPROGRESS, errno.EALREADY, errno.EWOULDBLOCK):
                    if self._writable.wait(self.gettimeout()):
                        raise socket.timeout("timed out")
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
        return SocketFile(self, mode)

    def recv(self, nbytes, flags=0):
        with self._registered('re'):
            while 1:
                if self._closed:
                    raise socket.error(errno.EBADF, "Bad file descriptor")
                try:
                    return self._sock.recv(nbytes, flags)
                except socket.error, e:
                    if self._blocking and e[0] in (
                            errno.EWOULDBLOCK, errno.EAGAIN):
                        if self._readable.wait(self.gettimeout()):
                            raise socket.timeout("timed out")
                        continue
                    if e[0] in SOCKET_CLOSED:
                        self._closed = True
                        return ''
                    raise

    def recv_into(self, buffer, nbytes=0, flags=0):
        with self._registered('re'):
            while 1:
                if self._closed:
                    raise socket.error(errno.EBADF, "Bad file descriptor")
                try:
                    return self._sock.recv_into(buffer, nbytes, flags)
                except socket.error, e:
                    if self._blocking and e[0] in (
                            errno.EWOULDBLOCK, errno.EAGAIN):
                        if self._readable.wait(self.gettimeout()):
                            raise socket.timeout("timed out")
                        continue
                    if e[0] in SOCKET_CLOSED:
                        self._closed = True
                        return
                    raise

    def recvfrom(self, nbytes, flags=0):
        with self._registered('re'):
            while 1:
                if self._closed:
                    raise socket.error(errno.EBADF, "Bad file descriptor")
                try:
                    return self._sock.recvfrom(nbytes, flags)
                except socket.error, e:
                    if self._blocking and e[0] in (
                            errno.EWOULDBLOCK, errno.EAGAIN):
                        if self._readable.wait(self.gettimeout()):
                            raise socket.timeout("timed out")
                        continue
                    if e[0] in SOCKET_CLOSED:
                        self._closed = True
                        return '', (None, 0)
                    raise

    def recvfrom_into(self, buffer, nbytes=0, flags=0):
        with self._registered('re'):
            while 1:
                if self._closed:
                    raise socket.error(errno.EBADF, "Bad file descriptor")
                try:
                    return self._sock.recvfrom_into(buffer, nbytes, flags=0)
                except socket.error, e:
                    if self._blocking and e[0] in (
                            errno.EWOULDBLOCK, errno.EAGAIN):
                        if self._readable.wait(self.gettimeout()):
                            raise socket.timeout("timed out")
                        continue
                    if e[0] in SOCKET_CLOSED:
                        self._closed = True
                        return '', (None, 0)
                    raise

    def send(self, data, flags=0):
        try:
            return self._sock.send(data)
        except socket.error, err:
            if err[0] in (errno.EWOULDBLOCK, errno.ENOTCONN):
                return 0
            raise

    def sendall(self, data, flags=0):
        with self._registered('we'):
            sent = self.send(data, flags)
            while sent < len(data):
                if self._blocking and self._writable.wait(self.gettimeout()):
                    raise socket.timeout("timed out")
                sent += self.send(data[sent:], flags)

    def sendto(self, *args):
        try:
            return self._sock.sendto(*args)
        except socket.error, err:
            if err[0] in (errno.EWOULDBLOCK, errno.ENOTCONN):
                return 0
            raise

    def setblocking(self, flag):
        self._blocking = bool(flag)

    def setsockopt(self, level, option, value):
        return self._sock.setsockopt(level, option, value)

    def shutdown(self, flag):
        return self._sock.shutdown(flag)

    def settimeout(self, timeout):
        if timeout is not None:
            timeout = float(timeout)
        self._timeout = timeout


class SocketFile(FileBase):
    def __init__(self, sock, mode='b', bufsize=-1):
        super(SocketFile, self).__init__()
        self._sock = sock
        self.mode = mode
        if bufsize > 0:
            self.CHUNKSIZE = bufsize

    def close(self):
        self._sock.close()

    def fileno(self):
        return self._sock.fileno()

    def flush(self):
        pass

    def _read_chunk(self, size):
        return self._sock.recv(size)

    def _write_chunk(self, data):
        return self._sock.send(data)
