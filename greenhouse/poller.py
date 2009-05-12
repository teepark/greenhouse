import collections
import select

from greenhouse import _state


class BasePoller(object):
    NOT_PRESENT = object()
    SHORT_TIMEOUT = 0.0001

class EpollPoller(BasePoller):
    def __init__(self):
        self._poller = select.epoll()
        self.count = 0

    def register(self, fd, eventmask=BasePoller.NOT_PRESENT):
        self.count += 1
        fd = isinstance(fd, int) and fd or fd.fileno()
        if eventmask is self.NOT_PRESENT:
            return self._poller.register(fd)
        return self._poller.register(fd, eventmask)

    def unregister(self, fd):
        self.count -= 1
        fd = isinstance(fd, int) and fd or fd.fileno()
        self._poller.unregister(fd)

    def poll(self, timeout=BasePoller.SHORT_TIMEOUT):
        return self._poller.poll(timeout)

if hasattr(select, 'epoll'):
    EpollPoller.INMASK = select.EPOLLIN
    EpollPoller.OUTMASK = select.EPOLLOUT
    EpollPoller.ERRMASK = select.EPOLLERR

class PollPoller(BasePoller):
    def register(self, fd, eventmask=BasePoller.NOT_PRESENT):
        fd = isinstance(fd, int) and fd or fd.fileno()
        if event is self.NOT_PRESENT:
            return self._poller.register(fd)
        return self._poller.register(fd, eventmask)

    def unregister(self, fd):
        fd = isinstance(fd, int) and fd or fd.fileno()
        self._poller.unregister(fd)

    def poll(self, timeout=BasePoller.SHORT_TIMEOUT):
        return self._poller.poll(timeout)

if hasattr(select, 'poll'):
    PollPoller.INMASK = select.POLLIN
    PollPoller.OUTMASK = select.POLLOUT
    PollPoller.ERRMASK = select.POLLERR

class SelectPoller(BasePoller):
    INMASK = 1
    OUTMASK = 2
    ERRMASK = 4

    def __init__(self):
        self._fds = {}

    def register(self, fd, eventmask=BasePoller.NOT_PRESENT):
        fd = isinstance(fd, int) and fd or fd.fileno()
        if eventmask is self.NOT_PRESENT:
            eventmask = self.SELECTIN | self.SELECTOUT | self.SELECTERR
        isnew = fd not in self._fds
        self._fds[fd] = eventmask
        return isnew

    def unregister(self, fd):
        fd = isinstance(fd, int) and fd or fd.fileno()
        del self._fds[fd]

    def poll(self, timeout=BasePoller.SHORT_TIMEOUT):
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

def bestpoller():
    if hasattr(select, 'epoll'):
        return EpollPoller()
    elif hasattr(select, 'poll'):
        return PollPoller()
    return SelectPoller()

def setpoller(klass=None):
    _state.poller = klass or bestpoller()
setpoller()
