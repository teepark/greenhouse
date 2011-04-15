from __future__ import absolute_import

import errno

try:
    import zmq
    from ..ext import zmq as gzmq
except ImportError:
    zmq = gzmq = None


if zmq:
    _zmq_context = zmq.Context
    _zmq_socket = zmq.Socket
    _zmq_poller = zmq.Poller

    class ZMQContext(_zmq_context):
        def socket(self, sock_type):
            return ZMQSocket(self, sock_type)

    class ZMQSocket(_zmq_socket):
        def send(self, msg, flags=0):
            if flags & zmq.NOBLOCK:
                return super(ZMQSocket, self).send(msg, flags)
            flags |= zmq.NOBLOCK

            while 1:
                try:
                    return super(ZMQSocket, self).send(msg, flags)
                except zmq.ZMQError, exc:
                    if exc.errno != errno.EAGAIN:
                        raise
                    gzmq.wait_socks([(self, 2)])

        def recv(self, flags=0, copy=True, track=False):
            if flags & zmq.NOBLOCK:
                return super(ZMQSocket, self).recv(flags, copy, track)
            flags |= zmq.NOBLOCK

            while 1:
                try:
                    return super(ZMQSocket, self).recv(flags, copy, track)
                except zmq.ZMQError, exc:
                    if exc.errno != errno.EAGAIN:
                        raise
                    gzmq.wait_socks([(self, 1)])

    class ZMQPoller(object):
        def __init__(self):
            self._registry = {}

        def register(self, socket, flags=zmq.POLLIN | zmq.POLLOUT):
            self._registry[socket] = flags

        modify = register

        def unregister(self, socket):
            del self._registry[socket]

        def poll(self, timeout=None):
            return gzmq.wait_socks(self._registry.items(),
                    inmask=zmq.POLLIN, outmask=zmq.POLLOUT, timeout=timeout)


_zmq_patchers = {}
_zmq_core_patchers = {}
_zmq_core_context_patchers = {}
_zmq_core_socket_patchers = {}
_zmq_core_poll_patchers = {}

if zmq:
    _zmq_patchers.update({
        'Context': ZMQContext,
        'Socket': ZMQSocket,
        'Poller': ZMQPoller,
    })
    _zmq_core_patchers.update(_zmq_patchers)
    _zmq_core_context_patchers['Context'] = ZMQContext
    _zmq_core_socket_patchers['Socket'] = ZMQSocket
    _zmq_core_poll_patchers['Poller'] = ZMQPoller
