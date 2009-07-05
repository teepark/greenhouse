import collections
import errno
import fcntl
import functools
import os
import socket
import weakref
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from greenhouse import utils
from greenhouse._state import state


_socket = socket.socket

SOCKET_CLOSED = set((errno.ECONNRESET, errno.ENOTCONN, errno.ESHUTDOWN))

def monkeypatch():
    """replace functions in the standard library socket module
    with their non-blocking greenhouse equivalents"""
    socket.socket = Socket

def unmonkeypatch():
    "undo a call to monkeypatch()"
    socket.socket = _socket

#@utils._debugger
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
        if not hasattr(state, 'poller'):
            import greenhouse.poller
        state.poller.register(self._sock)

        # allow for lookup by fileno
        state.sockets[self._fileno].append(weakref.ref(self))

    def __del__(self):
        try:
            state.poller.unregister(self._sock)
        except:
            pass

    def accept(self):
        while 1:
            try:
                client, addr = self._sock.accept()
            except socket.error, err:
                if err[0] in (errno.EAGAIN, errno.EWOULDBLOCK):
                    pass
                else:
                    raise
            else:
                return type(self)(fromsock=client), addr
            self._readable.wait()

    def bind(self, *args, **kwargs):
        return self._sock.bind(*args, **kwargs)

    def close(self):
        self._closed = True
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

    def makefile(self, mode='r', bufsize=None):
        return socket._fileobject(self)

    def recv(self, nbytes):
        while 1:
            if self._closed:
                return ''
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

#@utils._debugger
class File(object):
    CHUNKSIZE = 8192
    NEWLINE = "\n"

    def __init__(self, name, mode='rb'):
        self.name = name
        self._buf = StringIO()
        self._pos = 0

        flags = os.O_RDWR
        if 'a' in mode:
            flags |= os.O_APPEND
        self._fno = fileno = os.open(name, flags)

        flags = fcntl.fcntl(fileno, fcntl.F_GETFL)
        fcntl.fcntl(fileno, fcntl.F_SETFL , flags | os.O_NONBLOCK)

    def close(self):
        os.close(self._fno)

    def fileno(self):
        return self._fno

    def _read_once(self, size):
        try:
            return os.read(self._fno, size)
        except (OSError, IOError), err:
            if err.args[0] in (errno.EAGAIN, errno.EINTR):
                return None
            else:
                raise

    def read(self, size=-1):
        chunksize = size < 0 and self.CHUNKSIZE or min(self.CHUNKSIZE, size)

        buf = self._buf
        buf.seek(0, 2)
        collected = buf.tell()

        while 1:
            if size >= 0 and collected <= size:
                # we have read enough already
                break

            output = self._read_once(chunksize)

            if output is None:
                # would have blocked
                scheduler.pause()
                continue

            if not output:
                # nothing more to read
                break

            collected += len(output)
            buf.write(output)

        # get rid of the old buffer
        rc = buf.getvalue()
        buf.seek(0)
        buf.truncate()

        # leave the overflow in the buffer
        if size >= 0:
            buf.write(rc[size:])
        return rc[:size]

    def readline(self):
        buf = self._buf
        buf.seek(0)
        newline, chunksize = self.NEWLINE, self.CHUNKSIZE

        text = buf.read()
        while text.find(newline) < 0:
            text = self.read(chunksize)
            if not text:
                break
            buf.write(text)

        rc = buf.getvalue()
        index = rc.find(newline)

        if index < 0:
            # no newline in the whole file, return everything
            index = len(rc)
        else:
            index += len(newline)

        buf.seek(0)
        buf.truncate()
        buf.write(rc[index:])
        return rc[:index]

    def xreadlines(self):
        line = self.readline()
        while line:
            yield line
            line = self.readline()

    def readline(self):
        return list(self.xreadlines())

    def seek(self, pos, modifier=0):
        os.lseek(self._fno, pos, modifier)

        # clear out the buffer
        buf = self._buf
        buf.seek(0)
        buf.truncate()

    def tell(self):
        return self._pos

    def _write_once(self, data):
        try:
            return os.write(self._fno, data)
        except (OSError, IOError), err:
            if err.args[0] in (errno.EAGAIN, errno.EINTR):
                return None
            else:
                raise

    def write(self, data):
        while data:
            went = self._write_once(data)
            if went is None:
                scheduler.pause()
                continue
            data = data[went:]

    def writelines(self, lines):
        for line in lines:
            self.write(line)
