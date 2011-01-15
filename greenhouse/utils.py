import bisect
import collections
import functools
from Queue import Empty, Full
import time
import weakref

from greenhouse import compat, scheduler


__all__ = ["Event", "Lock", "RLock", "Condition", "Semaphore",
           "BoundedSemaphore", "Timer", "Local", "Thread", "Queue", "Channel"]

def _debugger(cls):
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

    mirrors the standard library `threading.Event` API
    """
    def __init__(self):
        self._is_set = False
        self._waiters = []
        self._reset_timers(clear=False)

    def _reset_timers(self, clear=True):
        if clear:
            for timer in self._timers.itervalues():
                timer.cancel()
            self._timers.clear()
        else:
            self._timers = {}
        self._timer_counter = 1

    def _add_timer(self, timer):
        counter = self._timer_counter
        self._timer_counter += 1
        self._timers[counter] = timer
        return counter

    def _remove_timer(self, timer_key):
        return bool(self._timers.pop(timer_key, False))

    def is_set(self):
        """indicates whether waiting on the event will block right now

        :returns:
            ``True`` if the event has been :meth:`set` and waiting will not
            block, ``False`` if the event is :meth:`cleared<clear>` and
            :meth:`wait` will block
        """
        return self._is_set
    isSet = is_set

    def set(self):
        """set the event to triggered

        after calling this method, all greenlets waiting on the event will be
        rescheduled, and calling :meth:`wait` will not block until
        :meth:`clear` has been called
        """
        self._is_set = True
        scheduler.state.awoken_from_events.update(self._waiters)
        self._waiters = []
        self._reset_timers()

    def clear(self):
        """clear the event from being triggered

        after calling this method, waiting on this event will block until the
        :meth:`set` method has been called
        """
        self._is_set = False

    def wait(self, timeout=None):
        """pause the current coroutine until this event is set

        if :meth:`set` method has been called, this method will not block at
        all. otherwise it will block until :meth:`set` method is called

        :param timeout:
            the maximum amount of time to block in seconds. the default of
            ``None`` allows indefinite blocking.
        :type timeout: number or None

        :returns:
            ``True`` if a timeout was provided and was hit, otherwise ``False``
        """
        if self._is_set:
            return

        current = compat.getcurrent() # the waiting greenlet
        awoken = [False]

        if timeout is not None:
            @Timer.wrap(timeout)
            def timer():
                self._remove_timer(timer_key)
                awoken[0] = True
                self._waiters.remove(current)
                current.switch()

            timer_key = self._add_timer(timer)

        self._waiters.append(current)
        scheduler.state.mainloop.switch()

        return awoken[0]

#@_debugger
class Lock(object):
    """an object that can only be 'owned' by one greenlet at a time

    mirrors the standard library `threading.Lock` API
    """
    def __init__(self):
        self._locked = False
        self._owner = None
        self._waiters = collections.deque()

    def _is_owned(self):
        return self._owner is compat.getcurrent()

    def locked(self):
        """indicates whether the lock is currently locked

        :returns:
            ``True`` if the lock is locked (and therefore calling
            :meth:`acquire` would block), otherwise ``False``
        """
        return self._locked

    def acquire(self, blocking=True):
        """lock the lock, blocking until it becomes available

        :param blocking:
            whether to block if the lock is already owned (default ``True``)
        :type blocking: bool

        :returns:
            a `bool` indicating whether the lock was acquired. In the default
            case of ``blocking = True`` this will always be the case, but may
            not be otherwise.
        """
        current = compat.getcurrent()
        if not blocking:
            locked_already = self._locked
            if not locked_already:
                self._locked = True
                self._owner = current
            return not locked_already
        if self._locked:
            self._waiters.append(current)
            scheduler.state.mainloop.switch()
        else:
            self._locked = True
            self._owner = current
        return True

    def release(self):
        """open the lock back up to wake up a waiting greenlet

        :raises:
             `RuntimeError` if the calling greenlet is not the one that had
             :meth:`acquired <acquire>` the lock
        """
        if not self._locked:
            raise RuntimeError("cannot release un-acquired lock")
        if self._waiters:
            waiter = self._waiters.popleft()
            self._locked = True
            self._owner = waiter
            scheduler.state.awoken_from_events.add(waiter)
        else:
            self._locked = False
            self._owner = None

    def __enter__(self):
        return self.acquire()

    def __exit__(self, type, value, traceback):
        return self.release()

class RLock(Lock):
    """a lock which may be acquired more than once by the same greenlet

    mirrors the standard library `threading.RLock` API
    """
    def __init__(self):
        super(RLock, self).__init__()
        self._count = 0

    def acquire(self, blocking=True):
        """acquire ownership of the lock

        if the lock is already owned by the calling greenlet, a counter simply
        gets incremented. if it is owned by a different greenlet then it will
        block until the lock becomes available.

        :param blocking:
            whether to block if the lock is owned by a different greenlet
            (default ``True``)
        :type blocking: bool

        :returns:
            a `bool` indicating whether the lock was acquired. In the default
            case of ``blocking = True`` this will always be the case, but may
            not be otherwise.
        """
        current = compat.getcurrent()
        if self._owner is current:
            self._count += 1
            return True
        if self._locked and not blocking:
            return False
        if self._locked:
            self._waiters.append(compat.getcurrent())
            scheduler.state.mainloop.switch()
        else:
            self._locked = True
            self._owner = current
        self._count = 1
        return True

    def release(self):
        """release one ownership of the lock

        if the calling greenlet has :meth:`acquired <acquire>` the lock more
        than once this will simply decrement the counter. if this is a final
        release then a waiting greenlet is awoken

        :raises:
            `RuntimeError` if the calling greenlet is not the lock's owner
        """
        if not self._locked or self._owner is not compat.getcurrent():
            raise RuntimeError("cannot release un-acquired lock")
        self._count -= 1
        if self._count == 0:
            self._owner = None
            if self._waiters:
                waiter = self._waiters.popleft()
                self._locked = True
                self._owner = waiter
                scheduler.state.awoken_from_events.add(waiter)
            else:
                self._locked = False
                self._owner = None

class Condition(object):
    """a synchronization object capable of waking all or one of its waiters

    mirrors the standard library `threading.Condition` API

    :param lock: the lock object wrapped by the condition
    :type lock: :class:`Lock` or :class:`RLock`
    """
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

        :raises:
            `RuntimeError` if the underlying lock hasn't been
            :meth:`acquired <Lock.acquire>`
        """
        if not self._is_owned():
            raise RuntimeError("cannot wait on un-acquired lock")
        self._lock.release()

        current = compat.getcurrent()
        self._waiters.append(current)

        if timeout is not None:
            @Timer.wrap(timeout)
            def timer():
                self._waiters.remove(current)
                current.switch()

        scheduler.state.mainloop.switch()
        self._lock.acquire()

        if timeout is not None:
            timer.cancel()

    def notify(self, num=1):
        """wake one or more waiting greenlets

        :param num: the number of waiters to wake (default 1)
        :type num: int

        :raises:
            `RuntimeError` if the underlying lock hasn't been
            :meth:`acquired <Lock.acquire>`
        """
        if not self._is_owned():
            raise RuntimeError("cannot wait on un-acquired lock")
        for i in xrange(min(num, len(self._waiters))):
            scheduler.state.awoken_from_events.add(self._waiters.popleft())

    def notify_all(self):
        """wake all waiting greenlets

        :raises:
            `RuntimeError` if the underlying lock hasn't been
            :meth:`acquired <Lock.acquire>`
        """
        if not self._is_owned():
            raise RuntimeError("cannot wait on un-acquired lock")
        scheduler.state.awoken_from_events.update(self._waiters)
        self._waiters.clear()
    notifyAll = notify_all

class Semaphore(object):
    """a synchronization object with a counter that blocks when it reaches 0

    mirrors the api of `threading.Semaphore`

    :param value:
        the starting value of the counter
    :type value: int
    """
    def __init__(self, value=1):
        assert value >= 0, "semaphore value cannot be negative"
        self._value = value
        self._waiters = collections.deque()

    def acquire(self, blocking=True):
        """decrement the counter, blocking if it is already at 0

        :param blocking:
            whether or not to block if the counter is already at 0 (default
            ``True``)
        :type blocking: bool

        :returns:
            a bool, indicating whether the count was decremented (this can only
            be ``False`` if ``blocking`` was ``False`` -- otherwise it would
            have blocked until it could decrement the counter)
        """
        if self._value:
            self._value -= 1
            return True
        if not blocking:
            return False
        self._waiters.append(compat.getcurrent())
        scheduler.state.mainloop.switch()
        return True

    def release(self):
        "increment the counter, waking up a waiter if there was any"
        if self._waiters:
            scheduler.state.awoken_from_events.add(self._waiters.popleft())
        else:
            self._value += 1

    def __enter__(self):
        return self.acquire()

    def __exit__(self, type, value, traceback):
        return self.release()

class BoundedSemaphore(Semaphore):
    """a semaphore with an upper limit to the counter

    mirrors the api of `threading.BoundedSemaphore`

    :param value:
        the starting and maximum value of the counter
    :type value: int
    """
    def __init__(self, value=1):
        super(BoundedSemaphore, self).__init__(value)
        self._initial_value = value

    def release(self):
        """increment the counter, waking up a waiter if there was any

        :raises: `ValueError` if this increment would have crossed the maximum
        """
        if self._value >= self._initial_value:
            raise ValueError("BoundedSemaphore released too many times")
        return super(BoundedSemaphore, self).release()
    release.__doc__ = Semaphore.release.__doc__

class Timer(object):
    """creates a greenlet from a function and schedules it to run later

    mirrors the standard library `threading.Timer` API

    :param secs: how far in the future to defer running the function in seconds
    :type secs: int or float
    :param func: the function to run later
    :type func: function
    :param args: positional arguments to pass to the function
    :type args: tuple
    :param kwargs: keyword arguments to pass to the function
    :type kwargs: dict
    """
    def __init__(self, secs, func, args=(), kwargs=None):
        assert hasattr(func, "__call__"), "function argument must be callable"

        if args or kwargs:
            def run():
                return func(*args, **(kwargs or {}))
            self.run = run
        else:
            self.run = func

        self._glet = glet = scheduler.greenlet(self.run)

        self.waketime = waketime = time.time() + secs
        self.cancelled = False
        scheduler.schedule_at(waketime, glet)

    def cancel(self):
        """attempt to prevent the timer from ever running its function

        :returns:
            ``True`` if it was successful, ``False`` if the timer had already
            run or been cancelled
        """
        tp = scheduler.state.timed_paused
        if self.cancelled or not tp:
            return False
        self.cancelled = True
        index = bisect.bisect(tp, (self.waketime, None))
        if tp[index][1].run is self.run:
            tp[index:index + 1] = []
        else:
            try:
                scheduler.state.to_run.remove(self._glet)
            except ValueError:
                return False
        return True

    @classmethod
    def wrap(cls, secs, args=(), kwargs=None):
        """a classmethod decorator to immediately turn a function into a timer

        you won't find this on `threading.Timer`, it is an extension to that API

        this is a function *returning a decorator*, so it is used like so:

        >>> @Timer.wrap(5, args=("world",))
        >>> def say_hi_timer(name):
        ...     print "hello, %s" % name

        :param secs:
            how far in the future to defer running the function in seconds
        :type secs: int or float
        :param args: positional arguments to pass to the function
        :type args: tuple
        :param kwargs: keyword arguments to pass to the function
        :type kwargs: dict

        :returns: a decorator function
        """
        def decorator(func):
            return cls(secs, func, args, kwargs)
        return decorator

class Local(object):
    """an object that holds greenlet-local data

    mirrors the standard library `threading.local` API

    to use, simply create an instance with no arguments, and any attribute gets
    and sets will be specific to that greenlet
    """
    def __init__(self):
        object.__setattr__(self, "_local_data", weakref.WeakKeyDictionary())

    def __getattr__(self, name):
        local = self._local_data.setdefault(compat.getcurrent(), {})
        if name not in local:
            raise AttributeError, "Local object has no attribute %s" % name
        return local[name]

    def __setattr__(self, name, value):
        self._local_data.setdefault(compat.getcurrent(), {})[name] = value

class Thread(object):
    """a standin class for threads, but powered by greenlets

    this class is useful for :mod:`monkey-patching <greenhouse.emulation>`
    the standard library, but for code written explicitly for greenhouse, the
    functions in :mod:`greenhouse.scheduler` are a better way to go

    mirrors the standard library `threading.Thread` API

    :param group:
        this argument does nothing and must be ``None`` (for compatibility with
        the standard library `threading.Thread`)
    :type group: None
    :param target: the function to run in the greenlet
    :type target: function
    :param name: the thread name (defaults to a generated name)
    :type name: str
    :param args: positional arguments to pass in to the `target` function
    :type args: tuple
    :param kwargs: keyword arguments to pass to the `target` function
    :type kwargs: dict
    :param verbose: here for compatibility, it is actually ignored
    :type verbose: bool
    """
    def __init__(
            self,
            group=None,
            target=None,
            name=None,
            args=(),
            kwargs=None,
            verbose=None):
        assert group is None, "group argument must be None for now" #[sic]

        self._target = target
        self.name = str(name or self._newname())
        self._args = args or ()
        self._kwargs = kwargs or {}
        self._started = False
        self._finished = Event()
        self._glet = None
        # verbose is ignored

    def __repr__(self):
        status = "initial"
        if self._started:
            status = "started"
        if not self._finished.is_set():
            status = "stopped"
        return "<%s (%s, %s)>" % (type(self).__name__, self.name, status)

    def _activate(self):
        self._started = True
        type(self)._active[self._glet] = self

    def _deactivate(self):
        self._finished.set()
        type(self)._active.pop(self._glet)

    def start(self):
        """schedule to start the greenlet that runs this thread's function

        :raises: `RuntimeError` if the thread has already been started
        """
        if self._started:
            raise RuntimeError("thread already started")
        def run():
            try:
                self.run(*self._args, **self._kwargs)
            finally:
                self._deactivate()
        self._glet = scheduler.greenlet(run)
        scheduler.schedule(self._glet)
        self._activate()

    def run(self, *args, **kwargs):
        """override this method to define the thread's behavior

        this is an alternative way to define the thread's function than passing
        `target` to the constructor
        """
        self._target(*args, **kwargs)

    def join(self, timeout=None):
        """block until this thread terminates

        :param timeout:
            the maximum time to wait. with the default of ``None``, waits
            indefinitely
        :type timeout: int, float or None

        :raises:
            `RuntimeError` if called inside the thread, or it has not yet been
            started
        """
        if not self._started:
            raise RuntimeError("cannot join thread before it is started")
        if compat.getcurrent() is self._glet:
            raise RuntimeError("cannot join current thread")
        self._finished.wait(timeout)

    @property
    def ident(self):
        "unique identifier for this thread"
        return id(self._glet) if self._glet is not None else None

    def is_alive(self):
        """indicates whether the thread is currently running

        :returns:
            ``True`` if :meth:`start` has already been called but the function
            hasn't yet finished or been killed, ``False`` if it isn't currently
            running for any reason.
        """
        return self._started and not self._finished.is_set()
    isAlive = is_alive

    def is_daemon(self):
        """whether the thread is in daemonized mode

        :returns:
            ``False``. this is here for compatibility with `threading.Thread`,
            but daemonized mode is not supported.
        """
        return False
    isDaemon = is_daemon

    def set_daemon(self, daemonic):
        """here for compatibility with `threading.Thread`, this doesn't work

        :param daemonic: whether attempting to turn daemon mode on or off
        :type daemonic: bool

        :raises: `RuntimeError` when attempting to turn on daemonic mode
        """
        if daemonic:
            raise RuntimeError("green threads don't support daemonic operation")
    setDaemon = set_daemon

    daemon = property(is_daemon, set_daemon,
            doc="whether the thread is set as a daemon thread (unsupported)")

    def get_name(self):
        """the thread's name as passed in the constructor or :meth:`set_name`,
        or failing those the automatically generated name

        :returns: the thread's `str` name
        """
        return self.name
    getName = get_name

    def set_name(self, name):
        """overwrite the thread's name

        :param name: the name to set
        :type name: str
        """
        self.name = name
    setName = set_name

    _counter = 0

    @classmethod
    def _newname(cls):
        cls._counter += 1
        return "Thread-%d" % cls._counter

    _active = {}


def _enumerate_threads():
    return Thread._active.values()

def _active_thread_count():
    return len(Thread._active)

def _current_thread():
    return Thread._active.get(compat.getcurrent())


class Queue(object):
    """a producer-consumer queue

    :param maxsize:
        optional limit to the amount of queued data, after which :meth:`put`
        can block. the default of 0 turns off the limit, so :meth:`put` will
        never block
    :type maxsize: int

    mirrors the standard library `Queue.Queue` API
    """
    def __init__(self, maxsize=0):
        self._maxsize = maxsize
        self._waiters = collections.deque()
        self._data = collections.deque()
        self._open_tasks = 0
        self._jobs_done = Event()
        self._jobs_done.clear()

    def empty(self):
        """indicate whether there is any queued data

        :returns: ``True`` if there is data in the queue, otherwise ``False``
        """
        return not self._data

    def full(self):
        """indicate whether the queue has `maxsize` data queued

        :returns:
            ``True`` if the queue's data has reached `maxsize`, otherwise
            ``False``
        """
        return self._maxsize > 0 and len(self._data) == self._maxsize

    def get(self, blocking=True, timeout=None):
        """get an item out of the queue

        this method will block if `blocking` is ``True`` (default) and the
        queue is :meth:`empty`

        :param blocking:
            whether to block if there is no data yet available (default
            ``True``)
        :type blocking: bool
        :param timeout:
            the maximum time in seconds to block waiting for data. with the
            default of ``None``, can wait indefinitely. this is unused if
            `blocking` is ``False``.
        :type timeout: int, float or None

        :raises:
            :class:`Empty` if there is no data in the queue and blocking is
            ``False``, or `timeout` expires

        :returns: something that was previously :meth:`put` in the queue
        """
        if not self._data:
            if not blocking:
                raise Empty()

            glet = compat.getcurrent()
            self._waiters.append(glet)

            if timeout:
                @Timer.wrap(timeout)
                def timer():
                    self._waiters.remove(glet)
                    glet.throw(Empty)

            scheduler.state.mainloop.switch()

            if timeout:
                timer.cancel()

        if self.full() and self._waiters:
            scheduler.schedule(self._waiters.popleft())

        return self._data.popleft()

    def get_nowait(self):
        """get an item out of the queue without ever blocking

        this call is equivalent to ``get(blocking=False)``
        
        :returns: something that was previously :meth:`put` in the queue
        """
        return self.get(blocking=False)

    def put(self, item, blocking=True, timeout=None):
        """put an item into the queue
        
        if the queue was instantiated with a nonzero `maxsize` and that size
        has already been reached, this method will block until another greenlet
        :meth:`get`\ s an item out

        :param item: the object to put into the queue, can be any type
        :param blocking:
            whether to block if the queue is already :meth:`full` (default
            ``True``)
        :type blocking: bool
        :param timeout:
            the maximum time in seconds to block waiting. with the default of
            ``None``, it can wait indefinitely. this is unused if `blocking` is
            ``False``.
        :type timeout: int, float or None

        :raises:
            :class:`Full` if the queue is :meth:`full` and `blocking` is
            ``False``, or if `timeout` expires.
        """
        if self.full():
            if not blocking:
                raise Full()

            glet = compat.getcurrent()
            self._waiters.append(glet)

            if timeout:
                @Timer.wrap(timeout)
                def timer():
                    sef._waiters.remove(glet)
                    glet.throw(Full)

            scheduler.state.mainloop.switch()

            if timeout:
                timer.cancel()

        if self._waiters and not self.full():
            scheduler.schedule(self._waiters.popleft())

        if not self._open_tasks:
            self._jobs_done.clear()
        self._open_tasks += 1

        self._data.append(item)

    def put_nowait(self, item):
        """put an item into the queue without any chance of blocking
        
        this call is equivalent to ``put(blocking=False)``

        ;param item: the object to put into the queue, can be any type
        """
        return self.put(item, blocking=False)

    def qsize(self):
        """the number of queued pieces of data
        
        :returns: int
        """
        return len(self._data)

    def task_done(self):
        """mark that a "job" (corresponding to a :meth:`put` or
        :meth:`put_nowait` call) is finished
        
        the :meth:`join` method won't complete until the number of
        :meth:`task_done` calls equals the number of :meth:`put` calls
        """
        if not self._open_tasks:
            raise ValueError("task_done() called too many times")
        self._open_tasks -= 1
        if not self._open_tasks:
            self._jobs_done.set()

    def join(self, timeout=None):
        """wait for task completions

        blocks until either :meth:`task_done` has been called for every
        :meth:`put` call

        the queue is still usable after a :meth:`join` call. a return from
        :meth:`join` simply indicates that the queue has no jobs `currently`
        pending.

        :param timeout:
            the maximum amount of time to wait in seconds. the default of
            ``None`` allows indefinite waiting.
        :type timeout: int, float or None

        :returns:
            ``True`` if `timeout` was provided and expired, otherwise ``False``
        """
        return self._jobs_done.wait(timeout)


class Channel(object):
    """a pipe for inter-coroutine messaging

    mirrors Stackless Python's `stackless.channel` API
    """
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
        "indicates the # of senders (positive) or waiters (negative) blocked"
        return len(self._dataqueue) or -len(self._waiters)

    def close(self):
        "close the channel, ending new communications"
        self._closing = True

    @property
    def closed(self):
        "the channel has been closed, and all data received (read-only)"
        return self._closing and not self._dataqueue

    @property
    def closing(self):
        "the channel has been closed (read-only)"
        return self._closing

    def open(self):
        "allow communications again on a previously closed channel"
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

    preference = property(_get_preference, _set_preference, doc='''
        prefer senders (positive) or receivers (negative, default)

        if receivers are preferred, then on a channel with blocked receivers,
        a send() call will jump straight to the awoken receiver bypassing the
        scheduler entirely.

        similarly if senders are preferred, then with blocked senders receive()
        calls bypass the scheduler and jump straight to the awoken sender.

        a 0 preference always re-schedules awoken coroutines on both sides.
        '''.strip())

    @property
    def queue(self):
        'the first coroutine waiting on the channel, or None'
        return self._waiters[0] if self._waiters else None

    def receive(self):
        '''receive data on the channel.

        if there is a waiting sender, then re-schedule it and return its sent
        item now, otherwise block until another coroutine sends something.
        '''
        if self._closing and not self._dataqueue:
            raise StopIteration()
        if self._dataqueue:
            item = self._dataqueue.popleft()
            sender = self._waiters.popleft()
            if self.preference is 1:
                scheduler.schedule(compat.getcurrent())
                sender.switch()
            else:
                scheduler.schedule(sender)
            return item
        else:
            self._waiters.append(compat.getcurrent())
            scheduler.state.mainloop.switch()
            return self._dataqueue.pop()

    next = receive

    def send(self, item):
        '''send data over the channel.

        if there is a waiting receiver, re-schedule it and return immediately,
        otherwise block until there is a receiver to accept the item.
        '''
        if self._closing:
            raise RuntimeError("cannot send over a closing channel")
        if self._waiters and not self._dataqueue:
            self._dataqueue.append(item)
            if self.preference is -1:
                scheduler.schedule(compat.getcurrent())
                self._waiters.popleft().switch()
            else:
                scheduler.schedule(self._waiters.popleft())
        else:
            self._dataqueue.append(item)
            self._waiters.append(compat.getcurrent())
            scheduler.state.mainloop.switch()
