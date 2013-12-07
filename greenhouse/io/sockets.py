from __future__ import absolute_import, with_statement

import contextlib
import errno
import fcntl
import os
import socket
import sys

from .. import scheduler, util
from . import files


__all__ = ["Socket"]

_fcntl = fcntl.fcntl
_socket = socket.socket
_socketpair = socket.socketpair
_fromfd = socket.fromfd

_BLOCKING_OP = frozenset((
        errno.EINPROGRESS, errno.EAGAIN, errno.EWOULDBLOCK, errno.EALREADY))
_CANT_SEND = frozenset((errno.EWOULDBLOCK, errno.ENOTCONN))


class Socket(object):
    """a replacement class for the standard library's ``socket.socket``

    :class:`greenhouse.Socket<Socket>`\ s wrap the standard library's sockets,
    using the underlying socket in a non-blocking way and blocking the current
    coroutine where appropriate.

    They provide a totally matching API, however
    """
    def __init__(self, *args, **kwargs):
        sock = kwargs.pop('fromsock', None)
        if sock is None:
            sock = socket._realsocket(*args, **kwargs)
        while hasattr(sock, "_sock"):
            sock = sock._sock
        self._sock = sock

        # copy over attributes
        self._fileno = sock.fileno()
        self._timeout = sock.gettimeout()
        self._closed = False

        # make the underlying socket non-blocking
        fl = _fcntl(self._fileno, fcntl.F_GETFL)
        if 0 == fl & os.O_NONBLOCK:
            _fcntl(self._fileno, fcntl.F_SETFL, fl | os.O_NONBLOCK)

        # but by default, it blocks greenlets
        self._blocking = True

        # create events
        self._readable = util.Event()
        self._writable = util.Event()

    def _on_readable(self):
        self._readable.set()
        self._readable.clear()

    def _on_writable(self):
        self._writable.set()
        self._writable.clear()

    def _poller_evmask(self, poller, events):
        mask = 0
        rd, wr = False, False
        if 'r' in events:
            mask |= poller.INMASK
            rd = True
        if 'w' in events:
            mask |= poller.OUTMASK
            wr = True
        if 'e' in events:
            mask |= poller.ERRMASK
        return mask, rd, wr

    @contextlib.contextmanager
    def _registered(self, events=None):
        poller = scheduler.state.poller
        if events:
            events, rd, wr = self._poller_evmask(poller, events)
        try:
            counter = poller.register(self, events)
        except EnvironmentError, exc:
            tb = sys.exc_info()[2]
            if exc.args and exc.args[0] in errno.errorcode:
                raise socket.error, socket.error(*exc.args), tb
            raise

        rd = self._on_readable if rd else None
        wr = self._on_writable if wr else None
        scheduler._register_fd(self._fileno, rd, wr)

        try:
            yield
        finally:
            scheduler._unregister_fd(self._fileno, rd, wr)
            try:
                poller.unregister(self, counter)
            except EnvironmentError, exc:
                if exc.args and exc.args[0] in errno.errorcode:
                    raise socket.error(*exc.args)
                raise

    @property
    def family(self):
        return self._sock.family

    @property
    def proto(self):
        return self._sock.proto

    @property
    def type(self):
        return self._sock.type

    def accept(self):
        """accept a connection on the host/port to which the socket is bound

        .. note::

            if there is no connection attempt already queued, this method will
            block until a connection is made

        :returns:
            a two-tuple of ``(socket, address)`` where the socket is connected,
            and the address is the ``(ip_address, port)`` of the remote end
        """
        with self._registered('re'):
            while 1:
                try:
                    client, addr = self._sock.accept()
                except socket.error, exc:
                    if not self._blocking or exc[0] not in _BLOCKING_OP:
                        raise
                    sys.exc_clear()
                    if self._readable.wait(self.gettimeout()):
                        raise socket.timeout("timed out")
                    if scheduler.state.interrupted:
                        raise IOError(errno.EINTR,
                                "interrupted system call")
                    continue
                return type(self)(fromsock=client), addr

    def bind(self, address):
        """set the socket to operate on an address

        :param address:
            the address on which the socket will operate. the format of this
            argument depends on the socket's type; for TCP sockets, this is a
            ``(host, port)`` two-tuple
        """
        return self._sock.bind(address)

    def close(self):
        """close the current connection on the socket

        After this point all operations attempted on this socket will fail, and
        once any queued data is flushed, the remote end will not receive any
        more data
        """
        self._closed = True
        self._sock = socket._closedsocket()

    def connect(self, address):
        """initiate a new connection to a remote socket bound to an address

        .. note:: this method will block until the connection has been made

        :param address:
            the address to which to initiate a connection, the format of which
            depends on the socket's type; for TCP sockets, this is a
            ``(host, port``) two-tuple
        """
        address = _dns_resolve(self, address)
        with self._registered('we'):
            while 1:
                err = self._sock.connect_ex(address)
                if not self._blocking or err not in _BLOCKING_OP:
                    if err not in (0, errno.EISCONN):
                        raise socket.error(err, errno.errorcode[err])
                    return
                if self._writable.wait(self.gettimeout()):
                    raise socket.timeout("timed out")
                if scheduler.state.interrupted:
                    raise IOError(errno.EINTR,
                            "interrupted system call")

    def connect_ex(self, address):
        """initiate a connection without blocking

        :param address:
            the address to which to initiate a connection, the format of which
            depends on the socket's type; for TCP sockets, this is a
            ``(host, port)`` two-tuple

        :returns:
            the error code for the connection attempt -- 0 indicates success
        """
        return self._sock.connect_ex(_dns_resolve(self, address))

    def dup(self):
        """create a new copy of the current socket on the same file descriptor

        :returns: a new :class:`Socket`
        """
        return type(self)(fromsock=self._sock.dup())

    def fileno(self):
        """get the file descriptor

        :returns: the integer file descriptor of the socket
        """
        return self._fileno

    def getpeername(self):
        """address information for the remote end of a connection

        :returns:
            a representation of the address at the remote end of the
            connection, the format depends on the socket's type
        """
        return self._sock.getpeername()

    def getsockname(self):
        """address information for the local end of a connection

        :returns:
            a representation of the address at the local end of the connection,
            the format depends on the socket's type
        """
        return self._sock.getsockname()

    def getsockopt(self, level, optname, *args, **kwargs):
        """get the value of a given socket option

        the values for ``level`` and ``optname`` will usually come from
        constants in the standard library ``socket`` module. consult the unix
        manpage ``getsockopt(2)`` for more information.

        :param level: the level of the requested socket option
        :type level: int
        :param optname: the specific socket option requested
        :type optname: int
        :param buflen:
            the length of the buffer to use to collect the raw value of the
            socket option. if provided, the buffer is returned as a string and
            it is not parsed.
        :type buflen: int

        :returns: a string of the socket option's value
        """
        return self._sock.getsockopt(level, optname, *args, **kwargs)

    def gettimeout(self):
        """get the timeout set for this specific socket

        :returns:
            the number of seconds the socket's blocking operations should block
            before raising a ``socket.timeout`` in a float value
        """
        return self._timeout

    def listen(self, backlog):
        """listen for connections made to the socket

        :param backlog:
            the queue length for connections that haven't yet been
            :meth:`accept`\ ed
        :type backlog: int
        """
        return self._sock.listen(backlog)

    def makefile(self, mode='r', bufsize=-1):
        """create a file-like object that wraps the socket

        :param mode:
            like the ``mode`` argument for other files, indicates read ``'r'``,
            write ``'w'``, or both ``'r+'`` (default ``'r'``)
        :type mode: str
        :param bufsize:
            the length of the read buffer to use. 0 means unbuffered, < 0 means
            use the system default (default -1)
        :type bufsize: int

        :returns:
            a file-like object for which reading and writing sends and receives
            data over the socket connection
        """
        f = SocketFile(self._sock, mode)
        f._sock.settimeout(self.gettimeout())
        return f

    def recv(self, bufsize, flags=0):
        """receive data from the connection

        .. note:: this method will block until data is available to be read

        see the unix manpage for ``recv(2)`` for more information

        :param bufsize:
            the maximum number of bytes to receive. fewer may be returned,
            however
        :type bufsize: int
        :param flags:
            flags for the receive call. consult the unix manpage for
            ``recv(2)`` for what flags are available
        :type flags: int

        :returns: the data it read from the socket connection
        """
        with self._registered('re'):
            while 1:
                if self._closed:
                    raise socket.error(errno.EBADF, "Bad file descriptor")
                try:
                    return self._sock.recv(bufsize, flags)
                except socket.error, exc:
                    if not self._blocking or exc[0] not in _BLOCKING_OP:
                        raise
                    sys.exc_clear()
                    if self._readable.wait(self.gettimeout()):
                        raise socket.timeout("timed out")
                    if scheduler.state.interrupted:
                        raise IOError(errno.EINTR, "interrupted system call")

    def recv_into(self, buffer, bufsize=-1, flags=0):
        """receive data from the connection and place it into a buffer

        .. note:: this method will block until data is available to be read

        :param buffer:
            a sized buffer object to receive the data (this is generally an
            ``array.array('c', ...)`` instance)
        :param bufsize:
            the maximum number of bytes to receive. fewer may be returned,
            however. defaults to the size available in the provided buffer.
        :type bufsize: int
        :param flags:
            flags for the receive call. consult the unix manpage for
            ``recv(2)`` for what flags are available
        :type flags: int

        :returns: the number of bytes received and placed in the buffer
        """
        with self._registered('re'):
            while 1:
                if self._closed:
                    raise socket.error(errno.EBADF, "Bad file descriptor")
                try:
                    return self._sock.recv_into(buffer, bufsize, flags)
                except socket.error, exc:
                    if not self._blocking or exc[0] not in _BLOCKING_OP:
                        raise
                    sys.exc_clear()
                    if self._readable.wait(self.gettimeout()):
                        raise socket.timeout("timed out")
                    if scheduler.state.interrupted:
                        raise IOError(errno.EINTR, "interrupted system call")

    def recvfrom(self, bufsize, flags=0):
        """receive data on a socket that isn't necessarily a 1-1 connection

        .. note:: this method will block until data is available to be read

        :param bufsize:
            the maximum number of bytes to receive. fewer may be returned,
            however
        :type bufsize: int
        :param flags:
            flags for the receive call. consult the unix manpage for
            ``recv(2)`` for what flags are available
        :type flags: int

        :returns:
            a two-tuple of ``(data, address)`` -- the string data received and
            the address from which it was received
        """
        with self._registered('re'):
            while 1:
                if self._closed:
                    raise socket.error(errno.EBADF, "Bad file descriptor")
                try:
                    return self._sock.recvfrom(bufsize, flags)
                except socket.error, exc:
                    if not self._blocking or exc[0] not in _BLOCKING_OP:
                        raise
                    sys.exc_clear()
                    if self._readable.wait(self.gettimeout()):
                        raise socket.timeout("timed out")
                    if scheduler.state.interrupted:
                        raise IOError(errno.EINTR, "interrupted system call")

    def recvfrom_into(self, buffer, bufsize=-1, flags=0):
        """receive data on a non-TCP socket and place it in a buffer

        .. note:: this method will block until data is available to be read

        :param buffer:
            a sized buffer object to receive the data (this is generally an
            ``array.array('c', ...)`` instance)
        :param bufsize:
            the maximum number of bytes to receive. fewer may be returned,
            however. defaults to the size available in the provided buffer.
        :type bufsize: int
        :param flags:
            flags for the receive call. consult the unix manpage for
            ``recv(2)`` for what flags are available
        :type flags: int

        :returns:
            a two-tuple of ``(bytes, address)`` -- the number of bytes received
            and placed in the buffer, and the address it was received from
        """
        with self._registered('re'):
            while 1:
                if self._closed:
                    raise socket.error(errno.EBADF, "Bad file descriptor")
                try:
                    return self._sock.recvfrom_into(buffer, bufsize, flags=0)
                except socket.error, exc:
                    if not self._blocking or exc[0] not in _BLOCKING_OP:
                        raise
                    sys.exc_clear()
                    if self._readable.wait(self.gettimeout()):
                        raise socket.timeout("timed out")
                    if scheduler.state.interrupted:
                        raise IOError(errno.EINTR, "interrupted system call")

    def send(self, data, flags=0):
        """send data over the socket connection

        .. note:: this method may block if the socket's send buffer is full

        :param data: the data to send
        :type data: str
        :param flags:
            flags for the send call. this has the same meaning as for
            :meth:`recv`
        :type flags: int

        :returns:
            the number of bytes successfully sent, which may not necessarily be
            all the provided data
        """
        with self._registered('we'):
            while 1:
                try:
                    return self._sock.send(data)
                except socket.error, exc:
                    if exc[0] not in _CANT_SEND or not self._blocking:
                        raise
                    if self._writable.wait(self.gettimeout()):
                        raise socket.timeout("timed out")
                    if scheduler.state.interrupted:
                        raise IOError(errno.EINTR, "interrupted system call")

    def sendall(self, data, flags=0):
        """send data over the connection, and keep sending until it all goes

        .. note:: this method may block if the socket's send buffer is full

        :param data: the data to send
        :type data: str
        :param flags:
            flags for the send call. this has the same meaning as for
            :meth:`recv`
        :type flags: int
        """
        sent = self.send(data, flags)
        while sent < len(data):
            self.send(data[sent:], flags)

    def sendto(self, data, *args):
        """send data to a particular address

        .. note:: this method may block if the socket's send buffer is full

        :param data: the data to send
        :type data: str
        :param flags:
            flags for the send call. this has the same meaning as for
            :meth:`recv`. defaults to 0
        :type flags: int
        :param address:
            a representation of the address to which to send the data, the
            format depends on the socket's type
        """
        with self._registered('we'):
            while 1:
                try:
                    return self._sock.sendto(data, *args)
                except socket.error, exc:
                    if exc[0] not in _CANT_SEND or not self._blocking:
                        raise
                    if self._writable.wait(self.gettimeout()):
                        raise socket.timeout("timed out")
                    if scheduler.state.interrupted:
                        raise IOError(errno.EINTR, "interrupted system call")

    def setblocking(self, flag):
        """modify the behavior of blocking methods on the socket

        greenhouse sockets already ``setblocking(False)`` on the underlying
        standard python socket, but modifying this flag will affect the
        behavior of sockets either blocking the current coroutine or not.

        if this blocking is turned off, then blocking methods (such as
        :meth:`recv`) will raise the relevant exception when they would
        otherwise block the coroutine.

        :param flag: whether to enable or disable blocking
        :type flag: bool
        """
        self._blocking = bool(flag)

    def setsockopt(self, level, optname, value):
        """set the value of a given socket option

        the values for ``level`` and ``optname`` will usually come from
        constants in the standard library ``socket`` module. consult the unix
        manpage ``setsockopt(2)`` for more information.

        :param level: the level of the set socket option
        :type level: int
        :param optname: the specific socket option to set
        :type optname: int
        :param value: the value to set for the option
        :type value: int
        """
        return self._sock.setsockopt(level, optname, value)

    def shutdown(self, how):
        """close one or both ends of the connection

        :param how:
            the end(s) of the connection to shutdown. valid values are
            ``socket.SHUT_RD``, ``socket.SHUT_WR``, and ``socket.SHUT_RW``
            for shutting down the read end, the write end, or both respectively
        """
        return self._sock.shutdown(how)

    def settimeout(self, timeout):
        """set the timeout for this specific socket

        :param timeout:
            the number of seconds the socket's blocking operations should block
            before raising a ``socket.timeout``
        :type timeout: float or None
        """
        if timeout is not None:
            timeout = float(timeout)
        self._timeout = timeout


def socket_fromfd(fd, family, type_, *args):
    raw_sock = _fromfd(fd, family, type_, *args)
    return Socket(fromsock=raw_sock)


class SocketFile(files.FileBase):
    def __init__(self, sock, mode='b', bufsize=-1):
        super(SocketFile, self).__init__()
        self._sock = Socket(fromsock=sock)
        self.mode = mode
        if bufsize > 0:
            self.CHUNKSIZE = bufsize

    @property
    def closed(self):
        return isinstance(self._sock._sock, socket._closedsocket)

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


def _dns_resolve(sock, address):
    try:
        from ..ext import dns
    except ImportError:
        return address

    if not (sock.proto == socket.IPPROTO_IP and
            isinstance(address, tuple) and
            len(address) == 2 and
            address[0]):
        return address

    host, port = address
    pieces = host.split(".")
    if len(pieces) == 4 and all(
            x.isdigit() and 0 <= int(x) <= 255 for x in pieces):
        return address

    return dns.resolve(host)[0], port
