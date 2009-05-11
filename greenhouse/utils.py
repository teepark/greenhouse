from __future__ import with_statement

import threading

from greenhouse import globals
from greenhouse.compat import greenlet
from greenhouse import mainloop


class Event(object):
    _guidlock = threading.Lock()
    _guid = 1

    def __init__(self):
        with self._guidlock:
            self.id = self._guid
            self.__class__._guid += 1

    def wait(self):
        globals.events['paused'][self.id].append(greenlet.getcurrent())
        mainloop.go_to_next()

    def trigger(self):
        globals.events['awoken'].update(globals.events['paused'][self.id])
        del globals.events['paused'][self.id]


class Lock(object):
    def __init__(self):
        self._locked = False
        self._ev = Event()

    def locked(self):
        return self._locked

    def acquire(self, blocking=True):
        if not blocking:
            locked_already = self._locked
            self._locked = True
            return not locked_already
        while self._locked:
            self._ev.wait()
        self._locked = True
        return True

    def release(self):
        self._locked = False
        self._ev.trigger()

    def __enter__(self):
        return self.acquire()

    def __exit__(self, type, value, traceback):
        return self.release()

class RLock(Lock):
    def __init__(self):
        super(RLock, self).__init__()
        self._owner = greenlet.getcurrent()
        self._count = 0

    def acquire(self, blocking=True):
        current = greenlet.getcurrent()
        if self._owner is current:
            self._count += 1
            return True
        if self._locked and not blocking:
            return False
        while self._locked:
            self._ev.wait()
        self._owner = current
        self._locked = True
        self._count = 1
        return True

    def release(self):
        current = greenlet.getcurrent()
        if not self._locked or self._owner is not current:
            raise RuntimeError("cannot release un-acquired lock")
        self._count -= 1
        if self._count == 0:
            self._locked = False
            self._owner = None
            self._ev.trigger()
