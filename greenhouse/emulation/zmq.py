from __future__ import absolute_import

import errno

try:
    import zmq
    import zmq.core
    from ..ext import zmq as gzmq
except ImportError:
    zmq = gzmq = None

try:
    import zmq.core.poller as zcp
except ImportError:
    zcp = None

try:
    import zmq.sugar as zs
except ImportError:
    zs = None


if zmq:
    original_core_context = zmq.core.Context
    original_core_socket = zmq.core.Socket

    class ZMQContextGreenifier(object):
        def socket(self, sock_type):
            return self._SOCK_CLASS(self, sock_type)

    class ZMQSocketGreenifier(object):
        def send(self, msg, flags=0):
            if flags & zmq.NOBLOCK:
                return super(ZMQSocketGreenifier, self).send(msg, flags)
            flags |= zmq.NOBLOCK

            while 1:
                try:
                    return super(ZMQSocketGreenifier, self).send(msg, flags)
                except zmq.ZMQError, exc:
                    if exc.errno != errno.EAGAIN:
                        raise
                    gzmq.wait_socks([(self, 2)])

        def recv(self, flags=0, copy=True, track=False):
            if flags & zmq.NOBLOCK:
                return super(ZMQSocketGreenifier, self).recv(flags, copy, track)
            flags |= zmq.NOBLOCK

            while 1:
                try:
                    return super(ZMQSocketGreenifier, self).recv(
                            flags, copy, track)
                except zmq.ZMQError, exc:
                    if exc.errno != errno.EAGAIN:
                        raise
                    gzmq.wait_socks([(self, 1)])

    class ZMQCoreSocket(ZMQSocketGreenifier, original_core_socket):
        pass

    class ZMQCoreContext(ZMQContextGreenifier, original_core_context):
        _SOCK_CLASS = ZMQCoreSocket

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

    def zmq_poll(sockets, timeout=-1):
        if timeout < 0:
            timeout = None
        return gzmq.wait_socks(sockets,
                inmask=zmq.POLLIN, outmask=zmq.POLLOUT, timeout=timeout)

if zs:
    original_sugar_context = zmq.sugar.Context
    original_sugar_socket = zmq.sugar.Socket

    class ZMQSugarSocket(ZMQSocketGreenifier, original_sugar_socket):
        pass

    class ZMQSugarContext(ZMQContextGreenifier, original_sugar_context):
        _SOCK_CLASS = ZMQSugarSocket


patchers = {}
core_patchers = {}
core_context_patchers = {}
core_socket_patchers = {}
core_poll_patchers = {}
sugar_patchers = {}
sugar_context_patchers = {}
sugar_socket_patchers = {}
sugar_poll_patchers = {}

if zmq:
    patchers['Context'] = ZMQCoreContext
    patchers['Socket'] = ZMQCoreSocket
    patchers['zmq_poll'] = zmq_poll
    core_patchers.update(patchers)
    core_context_patchers['Context'] = ZMQCoreContext
    core_socket_patchers['Socket'] = ZMQCoreSocket

if zcp:
    patchers['Poller'] = ZMQPoller
    core_patchers['Poller'] = ZMQPoller
    core_poll_patchers['Poller'] = ZMQPoller

if zs:
    patchers['Context'] = ZMQSugarContext
    patchers['Socket'] = ZMQSugarSocket
    patchers['Poller'] = ZMQPoller
    sugar_patchers.update(patchers)
    sugar_context_patchers['Context'] = ZMQSugarContext
    sugar_socket_patchers['Socket'] = ZMQSugarSocket
    sugar_poll_patchers['Poller'] = ZMQPoller
