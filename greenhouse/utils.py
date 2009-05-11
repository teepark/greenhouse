from __future__ import with_statement

from greenhouse import globals
from greenhouse.compat import greenlet
from greenhouse import mainloop


class Event(object):
    def __init__(self):
        self._is_set = False

    def is_set(self):
        return self._is_set

    def set(self):
        self._is_set = True
        guid = id(self)
        globals.events['awoken'].update(globals.events['paused'][guid])
        del globals.events['paused'][guid]

    def clear(self):
        self._is_set = False

    def wait(self, timeout=None):
        if not self._is_set:
            guid = id(self)
            current = greenlet.getcurrent()
            globals.events['paused'][guid].append(current)
            if timeout is not None:
                def hit_timeout():
                    try:
                        globals.events['paused'][guid].remove(current)
                    except ValueError:
                        pass
                    else:
                        globals.events['awoken'].add(current)
                mainloop.schedule_in(timeout, hit_timeout)
            mainloop.go_to_next()

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
        if not self._locked:
            raise RuntimeError("cannot release un-acquired lock")
        self._locked = False
        self._ev.set()
        self._ev.clear()

    def __enter__(self):
        return self.acquire()

    def __exit__(self, type, value, traceback):
        return self.release()

class RLock(Lock):
    def __init__(self):
        super(RLock, self).__init__()
        self._owner = None
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
            self._ev.set()
            self._ev.clear()
