from __future__ import absolute_import

import time

from .. import poller, scheduler
from ..io import descriptor
import zmq.core


__all__ = ["wait_socks"]


def wait_socks(sock_events, inmask=1, outmask=2, timeout=None):
    """wait on a combination of zeromq sockets, normal sockets, and fds

    .. note:: this method can block

        it will return once there is relevant activity on any of the
        descriptors or sockets, or the timeout expires

    :param sock_events:
        two-tuples, the first item is either a zeromq socket, a socket, or a
        file descriptor, and the second item is a mask made up of the inmask
        and/or the outmask bitwise-ORd together
    :type sock_events: list
    :param inmask: the mask to use for readable events (default 1)
    :type inmask: int
    :param outmask: the mask to use for writable events (default 2)
    :type outmask: int
    :param timeout: the maximum time to block before raising an exception
    :type timeout: int, float or None

    :returns:
        a list of two-tuples, each has one of the first elements from
        ``sock_events``, the second element is the event mask of the activity
        that was detected (made up on inmask and/or outmask bitwise-ORd
        together)
    """
    results = []
    for sock, mask in sock_events:
        if isinstance(sock, zmq.core.Socket):
            mask = _check_events(sock, mask, inmask, outmask)
            if mask:
                results.append((sock, mask))
    if results:
        return results

    fd_map = {}
    fd_events = []
    for sock, mask in sock_events:
        if isinstance(sock, zmq.core.Socket):
            fd = sock.getsockopt(zmq.FD)
        elif isinstance(sock, int):
            fd = sock
        else:
            fd = sock.fileno()

        fd_map[fd] = sock
        fd_events.append((fd, mask))

    while 1:
        started = time.time()
        active = descriptor.wait_fds(fd_events, inmask, outmask, timeout)
        if not active:
            # timed out
            return []

        results = []
        for fd, mask in active:
            sock = fd_map[fd]
            if isinstance(sock, zmq.core.Socket):
                mask = _check_events(sock, mask, inmask, outmask)
                if not mask:
                    continue
            results.append((sock, mask))

        if results:
            return results

        timeout -= time.time() - started


def _check_events(sock, mask, inmask=1, outmask=2):
    evs = sock.getsockopt(zmq.EVENTS)
    result = 0
    if evs & zmq.POLLIN and mask & inmask:
        result |= inmask
    if evs & zmq.POLLOUT and mask & outmask:
        result |= outmask
    return result
