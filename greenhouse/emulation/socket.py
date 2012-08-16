from __future__ import absolute_import

import socket
try:
    from . import dns
except ImportError:
    dns = None

from .. import io


def green_socketpair(*args, **kwargs):
    a, b = io.sockets._socketpair(*args, **kwargs)
    return io.Socket(fromsock=a), io.Socket(fromsock=b)

def create_connection(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT,
        source_address=None):
    if dns:
        getaddrinfo = dns.getaddrinfo
    else:
        getaddrinfo = socket.getaddrinfo
    err = None
    for res in getaddrinfo(address[0], address[1], 0, socket.SOCK_STREAM):
        af, socktype, proto, canonname, sa = res
        sock = None
        try:
            sock = io.Socket(af, socktype, proto)
            if timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:
                sock.settimeout(timeout)
            if source_address:
                sock.bind(source_address)
            sock.connect(sa)
            return sock
        except socket.error, exc:
            err = exc

    if err is not None:
        raise err
    else:
        raise socket.error("getaddrinfo returns an empty list")


patchers = {
    'socket': io.Socket,
    'SocketType': io.Socket,
    'socketpair': green_socketpair,
    'create_connection': create_connection,
    'fromfd': io.sockets.socket_fromfd,
}
