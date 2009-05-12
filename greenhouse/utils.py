from __future__ import with_statement

import bisect
import collections
import time

from greenhouse import globals
from greenhouse.compat import greenlet
from greenhouse import mainloop


class Event(object):
    def __init__(self):
        self._is_set = False
        self._guid = id(self)

    def is_set(self):
        return self._is_set
    isSet = is_set

    def set(self):
        self._is_set = True
        globals.events['awoken'].update(globals.events['paused'][self._guid])
        del globals.events['paused'][self._guid]

    def clear(self):
        self._is_set = False

    def wait(self, timeout=None):
        if not self._is_set:
            current = greenlet.getcurrent()
            globals.events['paused'][self._guid].append(current)
            if timeout is not None:
                def hit_timeout():
                    try:
                        globals.events['paused'][self._guid].remove(current)
                    except ValueError:
                        pass
                    else:
                        globals.events['awoken'].add(current)
                mainloop.schedule_in(timeout, hit_timeout)
            mainloop.go_to_next()

class Lock(object):
    def __init__(self):
        self._locked = False
        self._event = Event()

    def locked(self):
        return self._locked

    def acquire(self, blocking=True):
        if not blocking:
            locked_already = self._locked
            self._locked = True
            return not locked_already
        while self._locked:
            self._event.wait()
        self._locked = True
        return True

    def release(self):
        if not self._locked:
            raise RuntimeError("cannot release un-acquired lock")
        self._locked = False
        self._event.set()
        self._event.clear()

    def __enter__(self):
        return self.acquire()

    def __exit__(self, type, value, traceback):
        return self.release()

class RLock(Lock):
    def __init__(self):
        super(RLock, self).__init__()
        self._owner = None
        self._count = 0

    def _is_owned(self):
        return self._owner is greenlet.getcurrent()

    def acquire(self, blocking=True):
        current = greenlet.getcurrent()
        if self._owner is current:
            self._count += 1
            return True
        if self._locked and not blocking:
            return False
        while self._locked:
            self._event.wait()
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
            self._event.set()
            self._event.clear()

class Condition(object):
    def __init__(self, lock=None):
        if lock is None:
            lock = RLock()
        self._lock = lock
        self._waiters = collections.deque()
        self.acquire = lock.acquire
        self.release = lock.release
        self.__enter__ = lock.__enter__
        self.__exit__ = lock.__exit__
        if hasattr(lock, '_is_owned'):
            self._is_owned = lock._is_owned

    def _is_owned(self):
        owned = not self._lock.acquire(False)
        self._lock.release()
        return owned

    def wait(self, timeout=None):
        if not self._is_owned():
            raise RuntimeError("cannot wait on un-acquired lock")
        self._lock.release()
        event = Event()
        self._waiters.append(event)
        event.wait()
        self._lock.acquire()

    def notify(self, num=1):
        if not self._is_owned():
            raise RuntimeError("cannot wait on un-acquired lock")
        for i in xrange(min(num, len(self._waiters))):
            self._waiters.popleft().set()

    def notify_all(self):
        if not self._is_owned():
            raise RuntimeError("cannot wait on un-acquired lock")
        self.notify(len(self._waiters))
    notifyAll = notify_all

class Semaphore(object):
    def __init__(self, value=1):
        assert value >= 0, "semaphore value cannot be negative"
        self._value = value
        self._waiters = collections.deque()

    def acquire(self, blocking=True):
        if self._value:
            self._value -= 1
            return True
        elif not blocking:
            return False
        event = Event()
        self._waiters.append(event)
        event.wait()
        return True

    def release(self):
        if self._value or not self._waiters:
            self._value += 1
        else:
            self._waiters.popleft().set()

    def __enter__(self):
        return self.acquire()

    def __exit__(self, type, value, traceback):
        return self.release()

class BoundedSemaphore(Semaphore):
    def __init__(self, value=1):
        super(BoundedSemaphore, self).__init__(value)
        self._initial_value = value
        self._upper_cond = Condition()

    def release(self):
        if self._value >= self._initial_value:
            raise ValueError("BoundedSemaphore released too many times")
        return super(BoundedSemaphore, self).release()

class Timer(object):
    def __init__(self, secs, func, args=(), kwargs=None):
        self.func = func
        self.args = args
        self.kwargs = kwargs or {}
        self._glet = glet = greenlet(self._run)
        self.waketime = waketime = time.time() + secs
        bisect.insort(globals.timed_paused, (waketime, glet))

    def cancel(self):
        tp = globals.timed_paused
        if not tp:
            return
        index = bisect.bisect(tp, (self.waketime, self._glet)) - 1
        if tp[index][1] is self._glet:
            tp[index:index + 1] = []

    def _run(self):
        return self.func(*self.args, **self.kwargs)
