import collections
import errno
import socket
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from greenhouse import utils, _state


_socket = socket.socket
_fromfd = socket.fromfd

def monkeypatch():
    """replace functions in the standard library socket module with their
    non-blocking greenhouse equivalents"""
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

        # share certain properties by filenumber, not socket instance
        socksforfd = _state.sockets[self._fileno]
        if socksforfd:
            copyfrom = socksforfd[0]
            self._readable = copyfrom._readable
            self._writable = copyfrom._writable
            self._timeout = copyfrom._timeout
            self._closed = copyfrom._closed
            self._recvbuf = copyfrom._recvbuf
        else:
            # make the underlying socket non-blocking
            self._sock.setblocking(False)

            # create events
            self._readable = utils.Event()
            self._writable = utils.Event()

            # some more housekeeping
            self._timeout = None
            self._closed = False
            self._recvbuf = StringIO()

            # register this socket for polling events
            if not hasattr(_state, 'poller'):
                import greenhouse.poller
            _state.poller.register(self._sock)

        # for looking up by file number
        socksforfd.append(self)

    def __del__(self):
        try:
            _state.poller.unregister(self._sock)
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
        for sock in _state.sockets[self._fileno]:
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

    def makefile(self, mode='r', bufsize=-1):
        return File(self, mode, bufsize)

    def setblocking(self, flag):
        return self._sock.setblocking(flag)

    def setsockopt(self, level, option, value):
        return self._sock.setsockopt(level, option, value)

    def shutdown(self, flag):
        return self._sock.shutdown(flag)

    def settimeout(self, timeout):
        for sock in _state.sockets[self._fileno]:
            sock._timeout = timeout

class File(object):
    CHUNKSIZE = 8192
    ENDLINE = '\r\n'

    def __init__(self, fd, mode='r', bufsize=-1):
        self._fileno = isinstance(fd, int) and fd or fd.fileno()
        _state.sockets[self._fileno].append(self)
        self._closed = False
        self._sock = self._getsock(fd)
        self.mode = mode
        self.bufsize = bufsize

    @staticmethod
    def _getsock(fp):
        if isinstance(fp, Socket):
            return fp
        for sock in _state.sockets[fp]:
            if isinstance(sock, Socket):
                return sock
        return fromfd(fp, socket.AF_INET, socket.SOCK_STREAM)

    def close(self):
        if self._closed:
            return
        for sock in _state.sockets[self._fileno]:
            sock._closed = True
        return self._sock.close()

    @property
    def closed(self):
        return self._closed

    def fileno(self):
        return self._fileno

    def flush(self):
        pass

    def _pull_left(self, size):
        buffer = self._sock._recvbuf
        contents = buffer.getvalue()
        buffer.seek(0)
        buffer.truncate()
        buffer.write(contents[size:])
        return contents[:size]

    def _pull_all(self):
        rc = buffer.getvalue()
        buffer.seek(0)
        buffer.truncate()
        return rc

    def read(self, size=-1):
        if size <= 0:
            return self._read_all()
        return self._read_upto(size)

    def _read_all(self):
        buffer = self._sock._recvbuf
        buffer.seek(0, 2)
        while 1:
            if self._sock._closed:
                rc = buffer.getvalue()
                buffer.seek(0)
                buffer.truncate()
                return rc
            chunk = self._sock.recv(self.CHUNKSIZE)
            buffer.write(chunk)
            if len(chunk) < self.CHUNKSIZE:
                rc = buffer.getvalue()
                buffer.seek(0)
                buffer.truncate()
                return rc

    def _read_upto(self, upto):
        buffer = self._sock._recvbuf
        buffer.seek(0, 2)
        size = upto
        size -= len(buffer.getvalue())
        if size <= 0:
            buffer.seek(0)
            rc = buffer.read(upto)
            leftover = buffer.read()
            buffer.seek(0)
            buffer.write(leftover)
            return rc
        while 1:
            if self._sock._closed:
                return buffer.getvalue()
            to_recv = min(size, self.CHUNKSIZE)
            chunk = self._sock.recv(to_recv)
            rcvd = len(chunk)
            size -= rcvd
            buffer.write(chunk)
            if rcvd < to_recv or size == 0:
                rc = buffer.getvalue()
                buffer.seek(0)
                buffer.truncate()
                return rc

    def readline(self):
        buffer = self._sock._recvbuf
        buffered = buffer.getvalue()
        buffer.seek(0, 2)
        index = buffered.find(self.ENDLINE)
        if index >= 0:
            index += len(self.ENDLINE)
            buffer.seek(0)
            buffer.truncate()
            buffer.write(buffered[index:])
            return buffered[:index]
        while 1: # established that the buffer doesn't contain a newline
            if self._sock._closed:
                rc = buffer.getvalue()
                buffer.seek(0)
                buffer.truncate()
                return rc
            chunk = self._sock.recv(self.CHUNKSIZE)
            if not chunk:
                rc = buffer.getvalue()
                buffer.seek(0)
                buffer.truncate()
                return rc
            index = chunk.find(self.ENDLINE)
            if index >= 0:
                index += len(self.ENDLINE)
                rc = buffer.getvalue() + chunk[:index]
                buffer.seek(0)
                buffer.truncate()
                buffer.write(chunk[index:])
                return rc
            # recv'd chunk doesn't contain a newline, recv again
            buffer.write(chunk)

    def xreadlines(self):
        buffer = self._sock._recvbuf
        buffered = buffer.getvalue()
        while 1:
            index = buffered.find(self.ENDLINE)
            if index >= 0:
                index += len(self.ENDLINE)
                yield buffered[:index]
                buffered = buffered[index:]
            else:
                break
        while 1:
            if self._sock._closed:
                yield buffer.getvalue()
                return
            chunk = self._sock.recv(self.CHUNKSIZE)
            index = chunk.find(self.ENDLINE)
            if len(chunk) < self.CHUNKSIZE:
                buffered += chunk
                break
            if index >= 0:
                index += len(self.ENDLINE)
                yield buffered + chunk[:index]
                buffered = chunk[index:]
        while 1:
            index = buffered.find(self.ENDLINE)
            if index >= 0:
                index += len(self.ENDLINE)
                yield buffered[:index]
                buffered = buffered[index:]
            else:
                yield buffered
                break

    __iter__ = xreadlines

    def readlines(self):
        return list(self.xreadlines())

    def write(self, data):
        self._sock.sendall(data)

    def writelines(self, lines):
        self._sock.sendall(''.join(lines))
