import bisect
import collections
import functools
import sys
import time
import weakref

from greenhouse.scheduler import state
from greenhouse.compat import greenlet
from greenhouse import scheduler


__all__ = ["Event", "Lock", "RLock", "Condition", "Semaphore",
           "BoundedSemaphore", "Timer", "Local", "Queue"]

def _debugger(cls): #pragma: no cover
    import types
    for name in dir(cls):
        attr = getattr(cls, name)
        if isinstance(attr, types.MethodType):
            def extrascope(attr):
                @functools.wraps(attr)
                def wrapper(*args, **kwargs):
                    print "%s.%s %s %s" % (cls.__name__, attr.__name__,
                            repr(args[1:]), repr(kwargs))
                    rc = attr(*args, **kwargs)
                    print "%s.%s --> %s" % (cls.__name__, attr.__name__,
                            repr(rc))
                    return rc
                return wrapper
            setattr(cls, name, extrascope(attr))
    return cls

#@_debugger
class Event(object):
    """an event for which greenlets can wait

    mirrors the standard library threading.Event API"""
    def __init__(self):
        self._is_set = False
        self._timeout_callbacks = []
        self._waiters = []
        self._active_timeouts = set()
        self._awoken_by_timeout = set()

    def is_set(self):
        "returns True if waiting on this event will block, False if not"
        return self._is_set
    isSet = is_set

    def set(self):
        """set the event to triggered

        after calling this method, all greenlets waiting on this event will be
        woken up, and calling wait() will not block until the clear() method
        has been called"""
        self._is_set = True
        self._active_timeouts.clear()
        state.awoken_from_events.update(self._waiters)
        self._waiters = []

    def clear(self):
        """clear the event from being triggered

        after calling this method, waiting on this event will block until the
        set() method has been called"""
        self._is_set = False

    def _add_timeout_callback(self, func):
        self._timeout_callbacks.append(func)

    def wait(self, timeout=None):
        """pause the current coroutine until this event is set

        if the set() method has been called, this method will not block at
        all. otherwise it will block until the set() method is called"""
        if self._is_set:
            return

        current = greenlet.getcurrent() # the waiting greenlet

        if timeout is not None:
            self._active_timeouts.add(current)

            @scheduler.schedule_in(timeout)
            def hit_timeout():
                if current in self._active_timeouts:
                    self._active_timeouts.remove(current)
                    self._awoken_by_timeout.add(current)
                    current.switch()

        self._waiters.append(current)
        state.mainloop.switch()

        if current in self._awoken_by_timeout:
            self._awoken_by_timeout.remove(current)

            klass, exc, tb = None, None, None
            for cb in self._timeout_callbacks:
                try:
                    cb()
                except Exception:
                    if klass is None:
                        klass, exc, tb = sys.exc_info()

            if klass is not None:
                raise klass, exc, tb

#@_debugger
class Lock(object):
    """an object that can only be 'owned' by one greenlet at a time

    mirrors the standard library threading.Lock API"""
    def __init__(self):
        self._locked = False
        self._owner = None
        self._waiters = collections.deque()

    def _is_owned(self):
        return self._owner is greenlet.getcurrent()

    def locked(self):
        "returns true if the lock is already 'locked' or 'owned'"
        return self._locked

    def acquire(self, blocking=True):
        "lock the lock, or block until it is available"
        current = greenlet.getcurrent()
        if not blocking:
            locked_already = self._locked
            self._locked = True
            if not locked_already:
                self._owner = current
            return not locked_already
        if self._locked:
            self._waiters.append(current)
            state.mainloop.switch()
        self._owner = current
        self._locked = True
        return True

    def release(self):
        "open the lock back up to wake up greenlets waiting on this lock"
        if not self._locked:
            raise RuntimeError("cannot release un-acquired lock")
        self._locked = False
        self._owner = None
        if self._waiters:
            state.awoken_from_events.add(self._waiters.popleft())

    def __enter__(self):
        return self.acquire()

    def __exit__(self, type, value, traceback):
        return self.release()

class RLock(Lock):
    """a lock which may be acquired more than once by the same greenlet

    mirrors the standard library threading.RLock API"""
    def __init__(self):
        super(RLock, self).__init__()
        self._count = 0

    def acquire(self, blocking=True):
        """if the lock is owned by a different greenlet, block until it is
        fully released. then increment the acquired count by one"""
        current = greenlet.getcurrent()
        if self._owner is current:
            self._count += 1
            return True
        if self._locked and not blocking:
            return False
        if self._locked:
            self._waiters.append(greenlet.getcurrent())
            state.mainloop.switch()
        self._owner = current
        self._locked = True
        self._count = 1
        return True

    def release(self):
        """decrement the owned count by one. if it reaches zero, fully release
        the lock, waking up a waiting greenlet"""
        if not self._locked or self._owner is not greenlet.getcurrent():
            raise RuntimeError("cannot release un-acquired lock")
        self._count -= 1
        if self._count == 0:
            self._owner = None
            if self._waiters:
                state.awoken_from_events.add(self._waiters.popleft())
            else:
                self._locked = False

class Condition(object):
    """a synchronization object capable of waking all or one of its waiters

    mirrors the standard library threading.Condition API"""
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
        if not owned:
            self._lock.release()
        return owned

    def wait(self, timeout=None):
        """wait to be woken up by the condition

        you must have acquired the underlying lock first"""
        if not self._is_owned():
            raise RuntimeError("cannot wait on un-acquired lock")
        self._lock.release()

        current = greenlet.getcurrent()
        self._waiters.append(current)

        if timeout is not None:
            @Timer.wrap(timeout)
            def timer():
                self._waiters.remove(current)
                current.switch()

        state.mainloop.switch()
        self._lock.acquire()

        if timeout is not None:
            timer.cancel()

    def notify(self, num=1):
        """wake up a set number (default 1) of the waiting greenlets

        you must have acquired the underlying lock first"""
        if not self._is_owned():
            raise RuntimeError("cannot wait on un-acquired lock")
        for i in xrange(min(num, len(self._waiters))):
            state.awoken_from_events.add(self._waiters.popleft())

    def notify_all(self):
        """wake up all the greenlets waiting on the condition

        you must have acquired the underlying lock first"""
        if not self._is_owned():
            raise RuntimeError("cannot wait on un-acquired lock")
        state.awoken_from_events.update(self._waiters)
        self._waiters.clear()
    notifyAll = notify_all

class Semaphore(object):
    """a synchronization object with a counter that blocks when it reaches 0

    mirrors the api of threading.Semaphore"""
    def __init__(self, value=1):
        assert value >= 0, "semaphore value cannot be negative"
        self._value = value
        self._waiters = collections.deque()

    def acquire(self, blocking=True):
        "lock or decrement the semaphore"
        if self._value:
            self._value -= 1
            return True
        elif not blocking:
            return False
        self._waiters.append(greenlet.getcurrent())
        state.mainloop.switch()
        return True

    def release(self):
        "release or increment the semaphore"
        if self._waiters:
            state.awoken_from_events.add(self._waiters.popleft())
        else:
            self._value += 1

    def __enter__(self):
        return self.acquire()

    def __exit__(self, type, value, traceback):
        return self.release()

class BoundedSemaphore(Semaphore):
    """a semaphore with an upper limit to the counter"""
    def __init__(self, value=1):
        super(BoundedSemaphore, self).__init__(value)
        self._initial_value = value

    def release(self):
        if self._value >= self._initial_value:
            raise ValueError("BoundedSemaphore released too many times")
        return super(BoundedSemaphore, self).release()
    release.__doc__ = Semaphore.release.__doc__

class Timer(object):
    """creates a greenlet from *func* and schedules it to run in *secs* seconds

    mirrors the standard library threading.Timer API"""
    def __init__(self, secs, func, args=(), kwargs=None):
        assert hasattr(func, "__call__"), "function argument must be callable"
        self.func = func
        self.args = args
        self.kwargs = kwargs

        self._glet = glet = greenlet(self.func, state.mainloop)

        self.waketime = waketime = time.time() + secs
        self.cancelled = False
        scheduler.schedule_at(waketime, glet)

    def cancel(self):
        "if called before the greenlet runs, stop it from ever starting"
        tp = state.timed_paused
        if self.cancelled or not tp:
            return False
        self.cancelled = True
        index = bisect.bisect(tp, (self.waketime, None))
        if tp[index][1].run is self.func:
            tp[index:index + 1] = []
        else:
            try:
                state.to_run.remove(self._glet)
            except ValueError:
                return False
        return True


    @classmethod
    def wrap(cls, secs, args=(), kwargs=None):
        "a classmethod decorator to immediately turn a function into a timer"
        def decorator(func):
            return cls(secs, func, args, kwargs)
        return decorator

class Local(object):
    """class that represents greenlet-local data

    mirrors the standard library threading.local API"""
    def __init__(self):
        object.__setattr__(self, "data", weakref.WeakKeyDictionary())

    def __getattr__(self, name):
        local = self.data.setdefault(greenlet.getcurrent(), {})
        if name not in local:
            raise AttributeError, "Local object has no attribute %s" % name
        return local[name]

    def __setattr__(self, name, value):
        self.data.setdefault(greenlet.getcurrent(), {})[name] = value


class Queue(object):
    """a producer-consumer queue

    mirrors the standard library Queue.Queue API"""
    class Empty(Exception):
        pass

    class Full(Exception):
        pass

    def __init__(self, maxsize=0):
        self._maxsize = maxsize
        self._waiters = collections.deque()
        self._data = collections.deque()
        self._open_tasks = 0
        self._jobs_done = Event()
        self._jobs_done.clear()

    def empty(self):
        "without blocking, returns True if the queue is empty"
        return not self._data

    def full(self):
        """returns True if the queue is full without blocking

        if the queue has no *maxsize*, this will always return False"""
        return self._maxsize > 0 and len(self._data) == self._maxsize

    def get(self, blocking=True, timeout=None):
        """get an item out of the queue

        if *blocking* is True (default), the method will block until an item is
        available, or until *timeout* seconds, whichever comes first. if it
        times out, it will raise a Queue.Empty exception

        if *blocking* is False, it will immediately either return an item or
        raise a Queue.Empty exception
        """
        if not self._data:
            if not blocking:
                raise self.Empty()

            glet = greenlet.getcurrent()
            self._waiters.append(glet)

            if timeout:
                @Timer.wrap(timeout)
                def timer():
                    self._waiters.remove(glet)
                    glet.throw(self.Empty)

            state.mainloop.switch()

            if timeout:
                timer.cancel()

        if self.full() and self._waiters:
            scheduler.schedule(self._waiters.popleft())

        return self._data.popleft()

    def get_nowait(self):
        "immediately return an item from the queue or raise Queue.Empty"
        return self.get(blocking=False)

    def put(self, item, blocking=True, timeout=None):
        """put an item into the queue

        if *blocking* is True (default) and the queue has a maxsize, the method
        will block until a spot in the queue has been made available, or
        *timeout* seconds has passed, whichever comes first. if it times out,
        it will raise a Queue.Full exception

        if *blocking* is False, it will immediately either place the item in
        the queue or raise a Query.Full exception"""
        if self.full():
            if not blocking:
                raise self.Full()

            glet = greenlet.getcurrent()
            self._waiters.append(glet)

            if timeout:
                @Timer.wrap(timeout)
                def timer():
                    sef._waiters.remove(glet)
                    glet.throw(self.Full)

            state.mainloop.switch()

            if timeout:
                timer.cancel()

        if self._waiters and not self.full():
            scheduler.schedule(self._waiters.popleft())

        if not self._open_tasks:
            self._jobs_done.clear()
        self._open_tasks += 1

        self._data.append(item)

    def put_nowait(self, item):
        "immediately place an item into the queue or raise Query.Full"
        return self.put(item, blocking=False)

    def qsize(self):
        "return the number of items in the queue, without blocking"
        return len(self._data)

    def task_done(self):
        "mark thata job (corresponding to a put() call) is finished"
        if not self._open_tasks:
            raise ValueError("task_done() called too many times")
        self._open_tasks -= 1
        if not self._open_tasks:
            self._jobs_done.set()

    def join(self):
        "block until every put() call has had a corresponding task_done() call"
        self._jobs_done.wait()


class Channel(object):
    def __init__(self):
        self._dataqueue = collections.deque()
        self._waiters = collections.deque()
        self._balance = 0
        self._preference = -1
        self._closing = False

    def __iter__(self):
        return self

    @property
    def balance(self):
        return self._dataqueue and len(self._dataqueue) or \
                -len(self._waiters)

    def close(self):
        self._closing = True

    @property
    def closed(self):
        return self._closing and not self._dataqueue

    @property
    def closing(self):
        return self._closing

    def open(self):
        self._closing = False

    def _get_preference(self):
        return self._preference

    def _set_preference(self, val):
        if val > 0:
            self._preference = 1
        elif val < 0:
            self._preference = -1
        else:
            self._preference = 0

    preference = property(_get_preference, _set_preference)

    @property
    def queue(self):
        return self._waiters and self._waiters[0] or None

    def receive(self):
        if self._closing and not self._dataqueue:
            raise StopIteration()
        if self._dataqueue:
            item = self._dataqueue.popleft()
            sender = self._waiters.popleft()
            if self.preference is 1:
                scheduler.schedule(greenlet.getcurrent())
                sender.switch()
            else:
                scheduler.schedule(sender)
            return item
        else:
            self._waiters.append(greenlet.getcurrent())
            state.mainloop.switch()
            return self._dataqueue.pop()

    next = receive

    def send(self, item):
        if self._waiters and not self._dataqueue:
            self._dataqueue.append(item)
            if self.preference is -1:
                scheduler.schedule(greenlet.getcurrent())
                self._waiters.popleft().switch()
            else:
                scheduler.schedule(self._waiters.popleft())
        else:
            self._dataqueue.append(item)
            self._waiters.append(greenlet.getcurrent())
            state.mainloop.switch()
