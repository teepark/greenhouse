from __future__ import absolute_import

import collections
import errno
import operator
import select
import sys


class Poll(object):
    "a greenhouse poller using the poll system call"
    INMASK = getattr(select, 'POLLIN', 0)
    OUTMASK = getattr(select, 'POLLOUT', 0)
    ERRMASK = getattr(select, 'POLLERR', 0) | getattr(select, "POLLHUP", 0)

    _POLLER = getattr(select, "poll", None)

    def __init__(self):
        self._poller = self._POLLER()
        self._registry = collections.defaultdict(dict)
        self._counter = 0

    def register(self, fd, eventmask=None):
        # integer file descriptor
        fd = fd if isinstance(fd, int) else fd.fileno()

        # mask nothing by default
        if eventmask is None:
            eventmask = self.INMASK | self.OUTMASK | self.ERRMASK

        # get the current registrations dictionary
        registrations = self._registry[fd]
        registered = reduce(
                operator.or_, registrations.itervalues(), 0)

        # update registrations in the OS poller
        self._update_registration(fd, registered, registered | eventmask)

        # store the registration
        self._counter += 1
        registrations[self._counter] = eventmask

        return self._counter

    def unregister(self, fd, counter):
        # integer file descriptor
        fd = fd if isinstance(fd, int) else fd.fileno()

        registrations = self._registry[fd]

        # allow for extra noop calls
        if counter not in registrations:
            self._registry.pop(fd)
            return

        mask = registrations.pop(counter)
        the_rest = reduce(operator.or_, registrations.itervalues(), 0)

        # update the OS poller's registration
        self._update_registration(fd, the_rest | mask, the_rest)

        if not registrations:
            self._registry.pop(fd)

    def poll(self, timeout):
        if timeout is not None:
            timeout *= 1000
        return self._poller.poll(timeout)

    def _update_registration(self, fd, from_mask, to_mask):
        if from_mask != to_mask:
            if from_mask:
                try:
                    self._poller.unregister(fd)
                except EnvironmentError, exc:
                    if exc.args[0] != errno.ENOENT:
                        raise
            if to_mask:
                self._poller.register(fd, to_mask)


class Epoll(Poll):
    "a greenhouse poller utilizing the 2.6+ stdlib's epoll support"
    INMASK = getattr(select, 'EPOLLIN', 0)
    OUTMASK = getattr(select, 'EPOLLOUT', 0)
    ERRMASK = getattr(select, 'EPOLLERR', 0) | getattr(select, "EPOLLHUP", 0)

    _POLLER = getattr(select, "epoll", None)

    def poll(self, timeout):
        if timeout is None:
            timeout = -1
        return self._poller.poll(timeout)


class KQueue(Poll):
    "a greenhouse poller using the 2.6+ stdlib's kqueue support"
    INMASK = 1
    OUTMASK = 2
    ERRMASK = 0

    _POLLER = getattr(select, "kqueue", None)

    _mask_map = {
        getattr(select, "KQ_FILTER_READ", 0): INMASK,
        getattr(select, "KQ_FILTER_WRITE", 0): OUTMASK,
    }

    def poll(self, timeout):
        evs = self._poller.control(None, 2 * len(self._registry), timeout)
        return [(ev.ident, self._mask_map[ev.filter]) for ev in evs]

    def _update_registration(self, fd, from_mask, to_mask):
        if from_mask == to_mask:
            return

        xor = from_mask ^ to_mask
        to_add = to_mask  & xor
        to_drop = from_mask & xor
        assert not to_add & to_drop # simple sanity

        events = []
        if to_add & self.INMASK:
            events.append(select.kevent(
                fd, select.KQ_FILTER_READ, select.KQ_EV_ADD))
        elif to_drop & self.INMASK:
            events.append(select.kevent(
                fd, select.KQ_FILTER_READ, select.KQ_EV_DELETE))
        if to_add & self.OUTMASK:
            events.append(select.kevent(
                fd, select.KQ_FILTER_WRITE, select.KQ_EV_ADD))
        elif to_drop & self.OUTMASK:
            events.append(select.kevent(
                fd, select.KQ_FILTER_WRITE, select.KQ_EV_DELETE))

        if events:
            if sys.platform == 'darwin':
                # busted OS X kqueue only accepts 1 kevent at a time
                for event in events:
                    self._poller.control([event], 0)
            else:
                self._poller.control(events, 0)


class Select(object):
    "a greenhouse poller using the select system call"
    INMASK = 1
    OUTMASK = 2
    ERRMASK = 4

    def __init__(self):
        self._registry = collections.defaultdict(dict)
        self._currentmasks = {}
        self._counter = 0

    def register(self, fd, eventmask=None):
        # integer file descriptor
        fd = fd if isinstance(fd, int) else fd.fileno()

        # mask nothing by default
        if eventmask is None:
            eventmask = self.INMASK | self.OUTMASK | self.ERRMASK

        # store the registration
        self._counter += 1
        self._registry[fd][self._counter] = eventmask

        # update the full mask
        self._currentmasks[fd] = self._currentmasks.get(fd, 0) | eventmask

        return self._counter

    def unregister(self, fd, counter):
        # integer file descriptor
        fd = fd if isinstance(fd, int) else fd.fileno()

        # just drop it from the registrations dict
        self._registry.get(fd, {}).pop(counter, None)

        # rewrite the full mask
        self._currentmasks[fd] = reduce(
                operator.or_, self._registry[fd].itervalues(), 0)

        if not self._registry[fd]:
            self._registry.pop(fd)

    def poll(self, timeout):
        rlist, wlist, xlist = [], [], []
        for fd, eventmask in self._currentmasks.iteritems():
            if eventmask & self.INMASK:
                rlist.append(fd)
            if eventmask & self.OUTMASK:
                wlist.append(fd)
            if eventmask & self.ERRMASK:
                xlist.append(fd)
        rlist, wlist, xlist = select.select(rlist, wlist, xlist, timeout)
        events = collections.defaultdict(int)
        for fd in rlist:
            events[fd] |= self.INMASK
        for fd in wlist:
            events[fd] |= self.OUTMASK
        for fd in xlist:
            events[fd] |= self.ERRMASK
        return events.items()


def best():
    if hasattr(select, 'epoll'):
        return Epoll()

    if hasattr(select, 'kqueue'):
        return KQueue()

    if hasattr(select, 'poll'):
        return Poll()

    return Select()
