import collections
import select

from greenhouse import _state


SHORT_TIMEOUT = 0.0001

class Epoll(object):
    "a greenhouse poller utilizing the 2.6+ stdlib's epoll support"
    INMASK = getattr(select, 'EPOLLIN', None)
    OUTMASK = getattr(select, 'EPOLLOUT', None)
    ERRMASK = getattr(select, 'EPOLLERR', None)
    def __init__(self):
        self._poller = select.epoll()

    def register(self, fd, eventmask=None):
        fd = isinstance(fd, int) and fd or fd.fileno()
        if eventmask is None:
            return self._poller.register(fd)
        return self._poller.register(fd, eventmask)

    def unregister(self, fd):
        fd = isinstance(fd, int) and fd or fd.fileno()
        self._poller.unregister(fd)

    def poll(self, timeout=SHORT_TIMEOUT):
        return self._poller.poll(timeout)

class Poll(object):
    "a greenhouse poller using the poll system call''"
    INMASK = getattr(select, 'POLLIN', None)
    OUTMASK = getattr(select, 'POLLOUT', None)
    ERRMASK = getattr(select, 'POLLERR', None)

    def __init__(self):
        self._poller = select.poll()

    def register(self, fd, eventmask=None):
        fd = isinstance(fd, int) and fd or fd.fileno()
        if event is None:
            return self._poller.register(fd)
        return self._poller.register(fd, eventmask)

    def unregister(self, fd):
        fd = isinstance(fd, int) and fd or fd.fileno()
        self._poller.unregister(fd)

    def poll(self, timeout=SHORT_TIMEOUT):
        return self._poller.poll(timeout)

class Select(object):
    "a greenhouse poller using the select system call"
    INMASK = 1
    OUTMASK = 2
    ERRMASK = 4

    def __init__(self):
        self._fds = {}

    def register(self, fd, eventmask=None):
        fd = isinstance(fd, int) and fd or fd.fileno()
        if eventmask is None:
            eventmask = self.SELECTIN | self.SELECTOUT | self.SELECTERR
        isnew = fd not in self._fds
        self._fds[fd] = eventmask
        return isnew

    def unregister(self, fd):
        fd = isinstance(fd, int) and fd or fd.fileno()
        del self._fds[fd]

    def poll(self, timeout=SHORT_TIMEOUT):
        rlist, wlist, xlist = [], [], []
        for fd, eventmask in self._fds.iteritems():
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
    elif hasattr(select, 'poll'):
        return Poll()
    return Select()

def set(poller=None):
    _state.poller = poller or best()
set()
