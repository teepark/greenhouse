from __future__ import with_statement

import errno
import fcntl
import os
import socket
import sys
import weakref
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from greenhouse import scheduler, utils


__all__ = ["File", "stdin", "stdout", "stderr"]

_open = open
_file = file


class FileBase(object):
    CHUNKSIZE = 8192
    NEWLINE = "\n"

    def __init__(self):
        self._rbuf = StringIO()

    def __iter__(self):
        line = self.readline()
        while line:
            yield line
            line = self.readline()

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()

    def read(self, size=-1):
        chunksize = size < 0 and self.CHUNKSIZE or min(self.CHUNKSIZE, size)

        buf = self._rbuf
        buf.seek(0, os.SEEK_END)
        collected = buf.tell()

        while 1:
            if size >= 0 and collected >= size:
                # we have read enough already
                break

            output = self._read_chunk(chunksize)
            if output is None:
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
        buf = self._rbuf
        newline, chunksize = self.NEWLINE, self.CHUNKSIZE
        buf.seek(0)

        text = buf.read()
        while text.find(newline) < 0:
            text = self._read_chunk(chunksize)
            if text is None:
                text = ''
                continue
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

    def readlines(self, bufsize=-1):
        return list(self.__iter__())

    def write(self, data):
        while data:
            went = self._write_chunk(data)
            if went is None:
                continue
            data = data[went:]

    def writelines(self, lines):
        self.write("".join(lines))

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


class File(FileBase):
    def __init__(self, name, mode='rb'):
        super(File, self).__init__()
        self.mode = mode
        self._closed = False

        # translate mode into the proper open flags
        flags = self._mode_to_flags(mode)

        # if write or append mode and the file doesn't exist, create it
        if flags & (os.O_WRONLY | os.O_RDWR) and not os.path.exists(name):
            _open(name, 'w').close()

        # open the file, get a descriptor
        try:
            self._fileno = os.open(name, flags)
        except OSError, exc:
            # stdlib open() raises IOError if the file doesn't exist, os.open
            # raises OSError. pfft, whatever.
            raise IOError(*exc.args)

        # try to drive the asyncronous waiting off of the polling interface,
        # but epoll doesn't seem to support filesystem descriptors, so fall
        # back to waiting with a simple yield
        self._set_up_waiting()

    def _set_up_waiting(self):
        try:
            counter = scheduler.state.poller.register(self)
            scheduler.state.poller.unregister(self, counter)
        except EnvironmentError:
            self._waiter = "_wait_yield"
        else:
            self._waiter = "_wait_event"
            self._readable = utils.Event()
            self._writable = utils.Event()
            scheduler.state.descriptormap[self._fileno].append(
                    weakref.ref(self))

    def _wait_event(self, reading):
        "wait on our events"
        if reading:
            counter = scheduler.state.poller.register(
                    self, scheduler.state.poller.INMASK)
            try:
                if self._readable.wait():
                    raise socket.timeout("timed out")
            finally:
                scheduler.state.poller.unregister(self, counter)
        else:
            counter = scheduler.state.poller.register(
                    self, scheduler.state.poller.OUTMASK)
            try:
                if self._writable.wait():
                    raise socket.timeout("timed out")
            finally:
                scheduler.state.poller.unregister(self, counter)

    def _wait_yield(self, reading):
        "generic busy wait, for when polling won't work"
        scheduler.pause()

    def _wait(self, reading):
        getattr(self, self._waiter)(reading)

    def _read_chunk(self, size):
        try:
            return os.read(self._fileno, size)
        except EnvironmentError, err:
            if err.args[0] in (errno.EAGAIN, errno.EINTR):
                self._wait(reading=True)
                return None
            raise

    def _write_chunk(self, data):
        try:
            return os.write(self._fileno, data)
        except EnvironmentError, err:
            if err.args[0] in (errno.EAGAIN, errno.EINTR):
                self._wait(reading=False)
                return None
            raise

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
        fp._rbuf = StringIO()
        fp._closed = False

        cls._add_flags(fd, cls._mode_to_flags(mode))
        fp._set_up_waiting()

        return fp

    def close(self):
        self._closed = True
        os.close(self._fileno)

    def fileno(self):
        return self._fileno

    def flush(self):
        return None

    def isatty(self):
        return self._fileno in (0, 1, 2)

    def seek(self, pos, modifier=0):
        os.lseek(self._fileno, pos, modifier)

        # clear out the buffer
        buf = self._rbuf
        buf.seek(0)
        buf.truncate()

    def tell(self):
        with os.fdopen(os.dup(self._fileno)) as fp:
            return fp.tell()


stdin = File.fromfd(getattr(sys.stdin, "fileno", lambda: 0)())
stdout = File.fromfd(getattr(sys.stdout, "fileno", lambda: 1)())
stderr = File.fromfd(getattr(sys.stderr, "fileno", lambda: 2)())
