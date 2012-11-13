from __future__ import absolute_import

import collections
import errno
import operator
import select
import sys

_original_select = select.select


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
        newmask = reduce(operator.or_,
                registrations.itervalues(), eventmask)

        # update registrations in the OS poller
        if registrations:
            self._poller.unregister(fd)
        self._poller.register(fd, newmask)

        # store the registration
        self._counter += 1
        registrations[self._counter] = eventmask

        return self._counter

    def unregister(self, fd, counter):
        # integer file descriptor
        fd = fd if isinstance(fd, int) else fd.fileno()

        registrations = self._registry[fd]

        del registrations[counter]
        oldmask = reduce(operator.or_, registrations.itervalues(), 0)

        # update the OS poller's registration
        self._poller.unregister(fd)
        if registrations:
            self._poller.register(fd, oldmask)
        else:
            del self._registry[fd]

    def poll(self, timeout):
        if timeout is not None:
            timeout *= 1000
        return self._poller.poll(timeout)


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

    def register(self, fd, eventmask=None):
        # integer file descriptor
        fd = fd if isinstance(fd, int) else fd.fileno()

        # mask nothing by default
        if eventmask is None:
            eventmask = self.INMASK | self.OUTMASK | self.ERRMASK

        # get the current registrations dictionary
        registrations = self._registry[fd]
        oldmask = reduce(operator.or_, registrations.itervalues(), 0)

        self._apply_events(fd, oldmask, oldmask | eventmask)

        self._counter += 1
        registrations[self._counter] = eventmask

        return self._counter

    def unregister(self, fd, counter):
        # integer file descriptor
        fd = fd if isinstance(fd, int) else fd.fileno()

        registrations = self._registry[fd]

        eventmask = registrations.pop(counter)
        oldmask = reduce(operator.or_, registrations.itervalues(), 0)

        self._apply_events(fd, oldmask | eventmask, oldmask)

        if not registrations:
            del self._registry[fd]

    def _apply_events(self, fd, oldmask, newmask):
        events = []

        if self.INMASK & newmask & ~oldmask:
            events.append(select.kevent(fd,
                select.KQ_FILTER_READ, select.KQ_EV_ADD))
        elif self.INMASK & oldmask & ~newmask:
            events.append(select.kevent(fd,
                select.KQ_FILTER_READ, select.KQ_EV_DELETE))

        if self.OUTMASK & newmask & ~oldmask:
            events.append(select.kevent(fd,
                select.KQ_FILTER_WRITE, select.KQ_EV_ADD))
        elif self.OUTMASK & oldmask & ~newmask:
            events.append(select.kevent(fd,
                select.KQ_FILTER_WRITE, select.KQ_EV_DELETE))

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
        newmask = reduce(
                operator.or_, self._registry[fd].itervalues(), 0)
        if newmask:
            self._currentmasks[fd] = newmask
        else:
            self._currentmasks.pop(fd, 0)

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
        rlist, wlist, xlist = _original_select(rlist, wlist, xlist, timeout)
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
