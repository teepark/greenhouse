import contextlib
import errno
import fcntl
import os
import socket
import stat
import weakref
try:
    from cStringIO import StringIO
except ImportError: #pragma: no cover
    from StringIO import StringIO

import greenhouse
from greenhouse import utils
from greenhouse._state import state


__all__ = ["Socket", "File", "monkeypatch", "unmonkeypatch", "pipe"]


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

        # make the underlying socket non-blocking
        self.setblocking(False)

        # create events
        self._readable = greenhouse.Event()
        self._writable = greenhouse.Event()

        # make sure these events raise socket.timeout upon timeout
        def timeout_callback():
            raise socket.timeout("timed out")
        self._readable._add_timeout_callback(timeout_callback)
        self._writable._add_timeout_callback(timeout_callback)

        # some more housekeeping
        self._timeout = None
        self._closed = False

        # allow for lookup by fileno
        state.descriptormap[self._fileno].append(weakref.ref(self))

    def __del__(self):
        try:
            state.poller.unregister(self)
            state.descriptormap.pop(self._fileno, None)
        except:
            pass

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
            if 'e' in events: #pragma: no cover
                mask |= poller.ERRMASK
        try:
            poller.register(self, mask)
        except (IOError, OSError), error: #pragma: no cover
            if error.args and error.args[0] in errno.errorcode:
                raise socket.error(*error.args)
            raise

        yield

        try:
            poller.unregister(self)
        except (IOError, OSError), error: #pragma: no cover
            if error.args and error.args[0] in errno.errorcode:
                raise socket.error(*error.args)
            raise

    def accept(self):
        with self._registered('r'):
            while 1:
                try:
                    client, addr = self._sock.accept()
                except socket.error, err:
                    if err[0] in (errno.EAGAIN, errno.EWOULDBLOCK):
                        self._readable.wait(self._timeout)
                        continue
                    else:
                        raise #pragma: no cover
                return type(self)(fromsock=client), addr

    def bind(self, *args, **kwargs):
        return self._sock.bind(*args, **kwargs)

    def close(self):
        # as much as this sucks, it's necessary for sufficient stdlib socket
        # compatibility to make httplib (and by extension urllib, urllib2)
        # work. the problem is it calls close(), then recv(). WTF
        pass

    def connect(self, address):
        with self._registered('w'):
            while True:
                err = self.connect_ex(address)
                if err in (errno.EINPROGRESS, errno.EALREADY,
                        errno.EWOULDBLOCK):
                    self._writable.wait(self._timeout)
                    continue
                if err not in (0, errno.EISCONN): #pragma: no cover
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
        return socket._fileobject(self, mode, bufsize)

    def recv(self, nbytes):
        with self._registered('r'):
            while 1:
                if self._closed:
                    raise socket.error(errno.EBADF, "Bad file descriptor")
                try:
                    return self._sock.recv(nbytes)
                except socket.error, e:
                    if e[0] in (errno.EWOULDBLOCK, errno.EAGAIN):
                        self._readable.wait(self._timeout)
                        continue
                    if e[0] in SOCKET_CLOSED:
                        self._closed = True
                        return ''
                    raise #pragma: no cover

    def recv_into(self, buffer, nbytes):
        with self._registered('r'):
            self._readable.wait(self._timeout)
            return self._sock.recv_into(buffer, nbytes)

    def recvfrom(self, nbytes):
        with self._registered('r'):
            self._readable.wait(self._timeout)
            return self._sock.recvfrom(nbytes)

    def recvfrom_into(self, buffer, nbytes):
        with self._registered('r'):
            self._readable.wait(self._timeout)
            return self._sock.recvfrom_into(buffer, nbytes)

    def send(self, data):
        try:
            return self._sock.send(data)
        except socket.error, err: #pragma: no cover
            if err[0] in (errno.EWOULDBLOCK, errno.ENOTCONN):
                return 0
            raise

    def sendall(self, data):
        with self._registered('w'):
            sent = self.send(data)
            while sent < len(data): #pragma: no cover
                self._writable.wait(self._timeout)
                sent += self.send(data[sent:])

    def sendto(self, *args):
        try:
            return self._sock.sendto(*args)
        except socket.error, err: #pragma: no cover
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
        try:
            state.poller.register(self)

            # if we got here, poller.register worked, so set up event-based IO
            self._waiter = "_wait_event"
            self._readable = greenhouse.Event()
            self._writable = greenhouse.Event()
            state.descriptormap[self._fileno].append(weakref.ref(self))
        except IOError:
            self._waiter = "_wait_yield"

    def __init__(self, name, mode='rb'):
        self.mode = mode
        self._buf = StringIO()
        self._closed = False

        # translate mode into the proper open flags
        flags = self._mode_to_flags(mode)

        # if write or append mode and the file doesn't exist, create it
        if flags & (os.O_WRONLY | os.O_RDWR) and not os.path.exists(name):
            greenhouse.mkfile(name)

        # open the file, get a descriptor
        try:
            self._fileno = os.open(name, flags)
        except OSError, exc:
            # stdlib open() raises IOError if the file doesn't exist, os.open
            # raises OSError. pfft, whatever.
            raise IOError(*exc.args)

        # try to drive the asyncronous waiting off of the polling interface,
        # but epoll doesn't seem to support filesystem descriptors, so fall
        # back to a waiting with a simple yield
        self._set_up_waiting()

    def _wait_event(self, reading): #pragma: no cover
        "wait on our events"
        if reading:
            self._readable.wait()
        else:
            self._writable.wait()

    def _wait_yield(self, reading): #pragma: no cover
        "generic wait, for when polling won't work"
        scheduler.pause()

    def _wait(self, reading):
        getattr(self, self._waiter)(reading)

    @staticmethod
    def _add_flags(fd, flags):
        fdflags = fcntl.fcntl(fd, fcntl.F_GETFL)
        if fdflags & flags != flags:
            fcntl.fcntl(fd, fcntl.F_SETFL, flags | fdflags)

    @classmethod
    def fromfd(cls, fd, mode='rb'):
        fp = object.__new__(cls) # bypass __init__
        fp.mode = mode
        fp._fileno = fd
        fp._buf = StringIO()
        fp._closed = False

        cls._add_flags(fd, cls._mode_to_flags(mode))
        fp._set_up_waiting()

        return fp

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
        self._closed = True
        os.close(self._fileno)
        state.poller.unregister(self)

    def fileno(self):
        return self._fileno

    def flush(self):
        return None

    def read(self, size=-1):
        chunksize = size < 0 and self.CHUNKSIZE or min(self.CHUNKSIZE, size)

        buf = self._buf
        buf.seek(0, os.SEEK_END)
        collected = buf.tell()

        while 1:
            if size >= 0 and collected >= size:
                # we have read enough already
                break

            try:
                output = os.read(self._fileno, chunksize)
            except (OSError, IOError), err: #pragma: no cover
                if err.args[0] in (errno.EAGAIN, errno.EINTR):
                    # would have blocked
                    self._wait(reading=True)
                    continue
                else:
                    raise

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
        newline, chunksize = self.NEWLINE, self.CHUNKSIZE
        buf.seek(0)

        text = buf.read()
        while text.find(newline) < 0:
            try:
                text = os.read(self._fileno, chunksize)
            except (OSError, IOError), err: #pragma: no cover
                if err.args[0] in (errno.EAGAIN, errno.EINTR):
                    # would have blocked
                    self._wait(reading=True)
                    continue
                else:
                    raise
            if not text:
                break
            buf.write(text)
        else:
            # found a newline
            rc = buf.getvalue()
            index = rc.find(newline) + len(newline)

            buf.seek(0)
            buf.truncate()
            buf.write(rc[index:])
            return rc[:index]

        # hit the end of the file, no more newlines
        rc = buf.getvalue()
        buf.seek(0)
        buf.truncate()
        return rc

    def readlines(self):
        return list(self.__iter__())

    def seek(self, pos, modifier=0):
        os.lseek(self._fileno, pos, modifier)

        # clear out the buffer
        buf = self._buf
        buf.seek(0)
        buf.truncate()

    def tell(self):
        with os.fdopen(os.dup(self._fileno)) as fp:
            return fp.tell()

    def write(self, data):
        while data:
            try:
                went = os.write(self._fileno, data)
            except (OSError, IOError), err: #pragma: no cover
                if err.args[0] in (errno.EAGAIN, errno.EINTR):
                    self._wait(reading=False)
                    continue
                else:
                    raise

            data = data[went:]

    def writelines(self, lines):
        self.write("".join(lines))

def pipe():
    r, w = os.pipe()
    return File.fromfd(r, 'rb'), File.fromfd(w, 'wb')
