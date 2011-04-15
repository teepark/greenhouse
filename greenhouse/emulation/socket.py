from __future__ import absolute_import

from .. import io


def _green_socketpair(*args, **kwargs):
    a, b = io.sockets._socketpair(*args, **kwargs)
    return io.Socket(fromsock=a), io.Socket(fromsock=b)


_socket_patchers = {
    'socket': io.Socket,
    'socketpair': _green_socketpair,
    'fromfd': io.sockets.socket_fromfd,
}
