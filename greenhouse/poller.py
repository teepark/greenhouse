import collections
import select

from greenhouse._state import state


__all__ = ["Epoll", "Poll", "Select", "best", "set"]

POLL_TIMEOUT = 0.01

class Poll(object):
    "a greenhouse poller using the poll system call''"
    INMASK = getattr(select, 'POLLIN', None)
    OUTMASK = getattr(select, 'POLLOUT', None)
    ERRMASK = getattr(select, 'POLLERR', None)

    _POLLER = getattr(select, "poll", None)

    def __init__(self):
        self._poller = self._POLLER()
        self._registry = collections.defaultdict(list)

    def register(self, fd, eventmask=None):
        # integer file descriptor
        fd = isinstance(fd, int) and fd or fd.fileno()

        # mask nothing by default
        if eventmask is None:
            eventmask = self.INMASK | self.OUTMASK | self.ERRMASK

        # get the mask of the current registration, if any
        registered = self._registry.get(fd)
        registered = registered and registered[-1] or 0

        # make sure eventmask includes all previous masks
        newmask = eventmask | registered

        # unregister the old mask
        if registered:
            self._poller.unregister(fd)

        # register the new mask
        rc = self._poller.register(fd, newmask)

        # append to a list of eventmasks so we can backtrack
        self._registry[fd].append(newmask)

        return rc

    def unregister(self, fd):
        # integer file descriptor
        fd = isinstance(fd, int) and fd or fd.fileno()

        # allow for extra noop calls
        if not self._registry.get(fd):
            return

        # unregister the current registration
        self._poller.unregister(fd)
        self._registry[fd].pop()

        # re-do the previous registration, if any
        newmask = self._registry[fd]
        newmask = newmask and newmask[-1]
        if newmask:
            self._poller.register(fd, newmask)
        else:
            self._registry.pop(fd)

    def poll(self, timeout=POLL_TIMEOUT):
        return self._poller.poll(timeout)

class Epoll(Poll):
    "a greenhouse poller utilizing the 2.6+ stdlib's epoll support"
    INMASK = getattr(select, 'EPOLLIN', None)
    OUTMASK = getattr(select, 'EPOLLOUT', None)
    ERRMASK = getattr(select, 'EPOLLERR', None)

    _POLLER = getattr(select, "epoll", None)

class Select(object):
    "a greenhouse poller using the select system call"
    INMASK = 1
    OUTMASK = 2
    ERRMASK = 4

    def __init__(self):
        self._registry = collections.defaultdict(list)
        self._currentmasks = {}

    def register(self, fd, eventmask=None):
        # integer file descriptor
        fd = isinstance(fd, int) and fd or fd.fileno()

        # mask nothing by default
        if eventmask is None:
            eventmask = self.INMASK | self.OUTMASK | self.ERRMASK

        # get the mask of the current registration, if any
        registered = self._registry.get(fd)
        registered = registered and registered[-1] or 0

        # make sure eventmask includes all previous masks
        newmask = eventmask | registered

        # apply the new mask
        self._currentmasks[fd] = newmask

        # append to the list of masks so we can backtrack
        self._registry[fd].append(newmask)

        return not registered

    def unregister(self, fd):
        # integer file descriptor
        fd = isinstance(fd, int) and fd or fd.fileno()

        # get rid of the last registered mask
        self._registry[fd].pop()

        # re-do the previous registration, if any
        if self._registry[fd]:
            self._currentmasks[fd] = self._registry[fd][-1]
        else:
            self._registry.pop(fd)
            self._currentmasks.pop(fd)

    def poll(self, timeout=POLL_TIMEOUT):
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
        for fd in xlist: #pragma: no cover
            events[fd] |= self.ERRMASK
        return events.items()

def best():
    if hasattr(select, 'epoll'):
        return Epoll()
    elif hasattr(select, 'poll'):
        return Poll()
    return Select()

def set(poller=None):
    state.poller = poller or best()
set()
