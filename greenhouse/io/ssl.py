from __future__ import absolute_import

import errno
import functools
import _socket
import socket
import _ssl
import ssl
import sys
import time

from greenhouse import poller, scheduler, util
from greenhouse.io import sockets as gsock


class SSLSocket(gsock.Socket):
    """socket-like object that speaks SSL/TLS

    this subclass of greenhouse.io.sockets.Socket wraps its underlying OS
    socket in an SSL context when necessary, and provides read and write
    methods over that channel

    mirrors the standard library ssl.SSLSocket api.
    """
    def __init__(self, sock, keyfile=None, certfile=None,
            server_side=False, cert_reqs=ssl.CERT_NONE,
            ssl_version=ssl.PROTOCOL_SSLv23, ca_certs=None,
            do_handshake_on_connect=True,
            suppress_ragged_eofs=True, ciphers=None):
        inner = sock
        while hasattr(getattr(inner, "_sock", None), "_sock"):
            inner = inner._sock
        self._sock = inner._sock if hasattr(inner, "_sock") else inner
        self._sock.setblocking(False)

        if ciphers is None and ssl_version != ssl._SSLv2_IF_EXISTS:
            ciphers = ssl._DEFAULT_CIPHERS

        if certfile and not keyfile:
            keyfile = certfile

        try:
            self.getpeername()
        except socket.error, exc:
            if exc.errno != errno.ENOTCONN:
                raise
            # not connected
            self._connected = False
            self._sslobj = None
        else:
            # connected, create the SSL object
            self._connected = True
            self._sslobj = _ssl.sslwrap(self._sock, server_side, keyfile,
                    certfile, cert_reqs, ssl_version, ca_certs, ciphers)

        self.keyfile = keyfile
        self.certfile = certfile
        self.cert_reqs = cert_reqs
        self.ssl_version = ssl_version
        self.ca_certs = ca_certs
        self.ciphers = ciphers
        self.do_handshake_on_connect = do_handshake_on_connect
        self.suppress_ragged_eofs = suppress_ragged_eofs

        if isinstance(inner, _socket.socket):
            self._timeout = socket.getdefaulttimeout()
        else:
            self._timeout = inner.gettimeout()
        if hasattr(inner, "_blocking"):
            self._blocking = inner._blocking
        else:
            self._blocking = True
        self._readable = util.Event()
        self._writable = util.Event()

        scheduler._register_fd(self.fileno(),
                self._on_readable, self._on_writable)

        if do_handshake_on_connect and self._connected:
            self.do_handshake(self._timeout)

    def _clone(self):
        clone = object.__new__(SSLSocket)
        clone._sock = self._sock
        clone.keyfile = self.keyfile
        clone.certfile = self.certfile
        clone.cert_reqs = self.cert_reqs
        clone.ssl_version = self.ssl_version
        clone.ca_certs = self.ca_certs
        clone.ciphers = self.ciphers
        clone.do_handshake_on_connect = self.do_handshake_on_connect
        clone.suppress_ragged_eofs = self.suppress_ragged_eofs
        clone._timeout = self._timeout
        clone._blocking = self._blocking
        clone._connected = self._connected
        clone._sslobj = self._sslobj
        clone._readable = util.Event()
        clone._writable = util.Event()
        scheduler._register_fd(clone.fileno(),
            clone._on_readable, clone._on_writable)
        return clone

    def settimeout(self, timeout):
        self._timeout = timeout

    def gettimeout(self):
        return self._timeout

    def _read_attempt(self, length):
        try:
            return self._sslobj.read(length)
        except ssl.SSLError, exc:
            if (exc.args[0] == ssl.SSL_ERROR_EOF
                    and self.suppress_ragged_eofs):
                return ''
            raise

    def read(self, len=1024):
        'read up to len bytes and return them, or empty string on EOF'
        return self._with_retry(
                functools.partial(self._read_attempt, len),
                self.gettimeout())

    def write(self, data):
        'write data to the ssl channel and return the # of bytes transferred'
        return self._with_retry(
                functools.partial(self._sslobj.write, data),
                self.gettimeout())

    def getpeercert(self, binary_form=False):
        """return a representation of the peer's certificate

        returns None if no certificate is in use by the peer
        returns {} if a certificate is in use, but was not validated
        """
        return self._sslobj.peer_certificate(binary_form)

    def cipher(self):
        if not self._sslobj:
            return None
        return self._sslobj.cipher()

    def send(self, data, flags=0):
        if self._sslobj:
            if flags != 0:
                raise ValueError(
                        "non-zero flags not allowed in calls to send() on %s" %
                        self.__class__)
            try:
                count = self._sslobj.write(data)
            except ssl.SSLError, exc:
                if exc.args[0] == ssl.SSL_ERROR_WANT_READ:
                    return 0
                if exc.args[0] == ssl.SSL_ERROR_WANT_WRITE:
                    return 0
                raise
            return count
        else:
            return self._sock.send(data, flags)

    def sendto(self, *args):
        if self._sslobj:
            raise ValueError("sendto not allowed on instances of %s" %
                    self.__class__)
        return self._sock.sendto(*args)

    def sendall(self, data, flags=0):
        tout = _timeout(self.gettimeout())
        if self._sslobj:
            if flags != 0:
                raise ValueError(
                    "non-zero flags not allowed in calls to sendall() on %s" %
                    self.__class__)
            sent = 0
            sent = self.send(data[sent:])
            while (sent < len(data)):
                if self._blocking:
                    self._wait_event(tout.now, write=True)
                sent += self.send(data[sent:])
            return sent
        else:
            return super(SSLSocket, self).sendall(self, data, flags)

    def recv(self, buflen=1024, flags=0):
        if self._sslobj:
            if flags != 0:
                raise ValueError(
                    "non-zero flags not allowed in calls to recv() on %s" %
                    self.__class__)
            return self.read(buflen)
        else:
            return self._sock.recv(buflen, flags)

    def recv_into(self, buffer, nbytes=None, flags=0):
        if buffer and (nbytes is None):
            nbytes = len(buffer)
        elif nbytes is None:
            nbytes = 1024
        if self._sslobj:
            if flags != 0:
                raise ValueError(
                  "non-zero flags not allowed in calls to recv_into() on %s" %
                  self.__class__)
            temp = self.read(nbytes)
            v = len(temp)
            buffer[:v] = temp
            return v
        else:
            return self._sock.recv_into(buffer, nbytes, flags)

    def recvfrom(self, buflen=1024, flags=0):
        if self._sslobj:
            raise ValueError("recvfrom not allowed on instances of %s" %
                             self.__class__)
        else:
            return self._sock.recvfrom(buflen, flags)

    def recvfrom_into(self, buffer, nbytes=None, flags=0):
        if self._sslobj:
            raise ValueError("recvfrom_into not allowed on instances of %s" %
                             self.__class__)
        else:
            return self._sock.recvfrom_into(buffer, nbytes, flags)

    def pending(self):
        if self._sslobj:
            return self._sslobj.pending()
        else:
            return 0

    def unwrap(self):
        if self._sslobj:
            s = self._sslobj.shutdown()
            self._sslobj = None
            return s
        else:
            raise ValueError("No SSL wrapper around " + str(self))

    def shutdown(self, how):
        self._sslobj = None
        socket.shutdown(self, how)

    def close(self):
        self._sslobj = None
        self._sock = socket._closedsocket()

    def do_handshake(self, timeout):
        'perform a SSL/TLS handshake'
        tout = _timeout(timeout)
        if not self._blocking:
            return self._sslobj.do_handshake()

        while 1:
            try:
                return self._sslobj.do_handshake()
            except ssl.SSLError, exc:
                if exc.args[0] == ssl.SSL_ERROR_WANT_READ:
                    self._wait_event(tout.now)
                    continue
                elif exc.args[0] == ssl.SSL_ERROR_WANT_WRITE:
                    self._wait_event(tout.now, write=True)
                    continue
                raise

        self._wait_event(timeout)
        self._sslobj.do_handshake()

    def connect_ex(self, address):
        'connects to the address and wraps the connection in an SSL context'
        return self._connect(address, self.gettimeout())

    def _connect(self, address, timeout):
        if self._connected:
            raise ValueError("attempt to connect already-connected SSLSocket!")
        self._sslobj = _ssl.sslwrap(self._sock, False, self.keyfile,
                self.certfile, self.cert_reqs, self.ssl_version,
                self.ca_certs, self.ciphers)

        err = super(SSLSocket, self).connect_ex(address)
        if err: return err

        try:
            if self.do_handshake_on_connect:
                self.do_handshake(timeout)
        except socket.error, exc:
            return exc.args[0]

        self._connected = True
        return 0

    def connect(self, address):
        'connects to the address and wraps the connection in an SSL context'
        tout = _timeout(self.gettimeout())
        while 1:
            self._wait_event(tout.now, write=True)
            err = self._connect(address, tout.now)
            if err in (errno.EINPROGRESS, errno.EALREADY, errno.EWOULDBLOCK):
                continue
            if err:
                raise socket.error(err, errno.errorcode[err])
            return 0

    def accept(self):
        """accept a connection attempt from a remote client

        returns a two-tuple with the ssl-context-wrapped connection,
        and the address of the remote client
        """
        while 1:
            try:
                sock, addr = self._sock.accept()
                return (type(self)(sock,
                    keyfile=self.keyfile,
                    certfile=self.certfile,
                    server_side=True,
                    cert_reqs=self.cert_reqs,
                    ssl_version=self.ssl_version,
                    ca_certs=self.ca_certs,
                    do_handshake_on_connect=self.do_handshake_on_connect,
                    suppress_ragged_eofs=self.suppress_ragged_eofs,
                    ciphers=self.ciphers), addr)
            except socket.error, exc:
                if exc.args[0] not in (errno.EAGAIN, errno.EWOULDBLOCK):
                    raise
                sys.exc_clear()
                self._wait_event(self.gettimeout())

    def makefile(self, mode='r', bufsize=-1):
        'return a file-like object that operates on the ssl connection'
        return gsock.SocketFile(self._clone(), mode)

    def _on_readable(self):
        self._readable.set()
        self._readable.clear()

    def _on_writable(self):
        self._writable.set()
        self._writable.clear()

    def _wait_event(self, timeout=None, write=False):
        poller = scheduler.state.poller
        mask = poller.ERRMASK | (poller.OUTMASK if write else poller.INMASK)
        event = self._writable if write else self._readable
        try:
            counter = poller.register(self, mask)
        except EnvironmentError, error:
            if error.args[0] in errno.errorcode:
                raise socket.error(*error.args)
            raise

        try:
            if event.wait(timeout):
                raise socket.timeout("timed out")
        finally:
            try:
                poller.unregister(self, counter)
            except EnvironmentError, error:
                if error.args[0] in errno.errorcode:
                    raise socket.error(*error.args)
                raise

    def _with_retry(self, func=None, timeout=None):
        if func is None:
            return lambda f: self._with_retry(f, timeout)

        tout = _timeout(timeout)
        while 1:
            try:
                return func()
            except ssl.SSLError, exc:
                if exc.args[0] == ssl.SSL_ERROR_WANT_READ:
                    self._wait_event(tout.now)
                elif exc.args[0] == ssl.SSL_ERROR_WANT_WRITE:
                    self._wait_event(tout.now, write=False)
                else:
                    raise


class _timeout(object):
    def __init__(self, timeout, exc=socket.timeout):
        if timeout is not None:
            self._deadline = time.time() + timeout
        self._timeout = timeout
        self._exc = exc

    @property
    def now(self):
        if self._timeout is None: return None
        timeout = self._deadline - time.time()
        if timeout < 0:
            raise self._exc('timed out')
        return timeout
