import errno
import fcntl
import os
import socket
import stat
import weakref
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from greenhouse import utils
from greenhouse._state import state


__all__ = ["Socket", "File", "monkeypatch", "unmonkeypatch"]


_socket = socket.socket
_open = __builtins__['open']
_file = __builtins__['file']

SOCKET_CLOSED = set((errno.ECONNRESET, errno.ENOTCONN, errno.ESHUTDOWN))

def monkeypatch():
    """replace functions in the standard library socket module
    with their non-blocking greenhouse equivalents"""
    socket.socket = Socket
    __builtins__['open'] = __builtins__['file'] = File

def unmonkeypatch():
    "undo a call to monkeypatch()"
    socket.socket = _socket
    __builtins__['open'] = _open
    __builtins__['file'] = _file

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
        state.poller.register(self)

        # allow for lookup by fileno
        state.descriptormap[self._fileno].append(weakref.ref(self))

    def __del__(self):
        try:
            state.poller.unregister(self)
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
        try:
            state.poller.unregister(self)
        except IOError, err:
            if err.args[0] != errno.ENOENT:
                raise
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

    @staticmethod
    def _mode_to_flags(mode):
        flags = os.O_RDONLY | os.O_NONBLOCK # always non-blocking
        if (('w' in mode or 'a' in mode) and 'r' in mode) or '+' in mode:
            # both read and write
            flags |= os.O_RDWR
        elif 'w' in mode or 'a' in mode:
            # else just write
            flags |= os.O_WRONLY

        if 'a' in mode:
            # append-write mode
            flags |= os.O_APPEND

        return flags

    def _set_up_waiting(self):
        if not hasattr(state, 'poller'):
            import greenhouse.poller
        try:
            state.poller.register(self)

            # if we got here, poller.register worked, so set up event-based IO
            self._wait = self._wait_event
            self._readable = utils.Event()
            self._writable = utils.Event()
            state.descriptormap[self._fileno].append(weakref.ref(self))
        except IOError:
            self._wait = self._wait_yield

    def __init__(self, name, mode='rb'):
        self.name = name
        self.mode = mode
        self._buf = StringIO()

        # translate mode into the proper open flags
        flags = self._mode_to_flags(mode)

        # if write or append mode and the file doesn't exist, create it
        if flags & (os.O_WRONLY | os.O_RDRW) and not os.path.exists(name):
            os.mknod(name, 0644, stat.S_IFREG)

        # open the file, get a descriptor
        self._fileno = fileno = os.open(name, flags)

        # try to drive the asyncronous waiting off of the polling interface,
        # but epoll doesn't seem to support filesystem descriptors, so fall
        # back to a waiting with a simple yield
        self._set_up_waiting()

    def _wait_event(self, reading):
        "wait on our events"
        if reading:
            self._readable.wait()
        else:
            self._writable.wait()

    def _wait_yield(self, reading):
        "generic wait, for when polling won't work"
        scheduler.pause()

    @classmethod
    def fromfd(cls, fd, mode='rb'):
        fp = object.__new__(cls)
        fp.mode = mode
        fp._fileno = fd
        fp._buf = StringIO()

        flags = cls._mode_to_flags(mode)

        fdflags = fcntl.fcntl(fd, FCNTL.F_GETFL)
        if fdflags & flags != flags:
            fcntl.fcntl(fd, FCNTL.F_SETFL, flags | fdflags)

        fp._set_up_waiting()

    def __iter__(self):
        line = self.readline()
        while line:
            yield line
            line = self.readline()

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()

    def __del__(self):
        try:
            state.poller.unregister(self)
        except:
            pass

    def close(self):
        os.close(self._fileno)
        state.poller.unregister(self)

    def fileno(self):
        return self._fileno

    def _read_once(self, size):
        try:
            return os.read(self._fileno, size)
        except (OSError, IOError), err:
            if err.args[0] in (errno.EAGAIN, errno.EINTR):
                return None
            else:
                raise

    def read(self, size=-1):
        chunksize = size < 0 and self.CHUNKSIZE or min(self.CHUNKSIZE, size)

        buf = self._buf
        buf.seek(0, os.SEEK_END)
        collected = buf.tell()

        while 1:
            if size >= 0 and collected >= size:
                # we have read enough already
                break

            output = self._read_once(chunksize)

            if output is None:
                # would have blocked
                self._wait(reading=True)
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

        if size >= 0:
            # leave the overflow in the buffer
            buf.write(rc[size:])
            return rc[:size]
        return rc

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

    def readlines(self):
        return list(self.__iter__())

    def seek(self, pos, modifier=0):
        os.lseek(self._fileno, pos, modifier)

        # clear out the buffer
        buf = self._buf
        buf.seek(0)
        buf.truncate()

    def tell(self):
        return os.fdopen(self._fileno).tell()

    def _write_once(self, data):
        try:
            return os.write(self._fileno, data)
        except (OSError, IOError), err:
            if err.args[0] in (errno.EAGAIN, errno.EINTR):
                return None
            else:
                raise

    def write(self, data):
        while data:
            went = self._write_once(data)
            if went is None:
                self._wait(reading=False)
                continue
            data = data[went:]

    def writelines(self, lines):
        for line in lines:
            self.write(line)

def pipe():
    r, w = os.pipe()
    r = File.fromfd(r, 'rb')
    w = File.fromfd(w, 'wb')

    return r, w
