import bisect
import collections
import errno
import operator
import sys
import time
import weakref

from greenhouse import compat, poller


__all__ = ["pause", "pause_until", "pause_for", "schedule", "schedule_at",
        "schedule_in", "schedule_recurring", "schedule_exception",
        "schedule_exception_at", "schedule_exception_in", "end",
        "global_exception_handler", "remove_global_exception_handler",
        "local_exception_handler", "remove_local_exception_handler",
        "handle_exception", "greenlet", "global_hook", "remove_global_hook",
        "local_incoming_hook", "remove_local_incoming_hook",
        "local_outgoing_hook", "remove_local_outgoing_hook",
        "set_ignore_interrupts", "reset_poller"]

BTREE_ORDER = 64


state = type('GreenhouseState', (), {})()

# from events that have triggered
state.awoken_from_events = set()

# executed a simple cooperative yield
state.paused = []

# map of file numbers to the sockets/files on that descriptor
state.descriptormap = collections.defaultdict(list)

# lined up to run right away
state.to_run = collections.deque()

# exceptions queued up for scheduled coros
state.to_raise = weakref.WeakKeyDictionary()

# exception handlers, global and local
state.global_exception_handlers = []
state.local_exception_handlers = weakref.WeakKeyDictionary()

# trace hook callbacks
state.global_hooks = []
state.local_to_hooks = weakref.WeakKeyDictionary()
state.local_from_hooks = weakref.WeakKeyDictionary()

# tracks interrupts
state.interrupted = False
state.ignore_interrupts = False


class TimeoutManager(object):
    def __nonzero__(self):
        return bool(self.data)

    def first(self):
        if self.data:
            return iter(self.data).next()
        return None

    @classmethod
    def install(cls):
        state.timed_paused = cls(state.timed_paused.dump())

class BisectingTimeoutManager(TimeoutManager):
    def __init__(self, data=None):
        self.data = data or []

    def clear(self):
        del self.data[:]

    def insert(self, unixtime, glet):
        bisect.insort(self.data, (unixtime, glet))

    def check(self):
        index = bisect.bisect(self.data, (time.time(), None))
        state.to_run.extend(pair[1] for pair in self.data[:index])
        self.data = self.data[index:]

    def remove(self, unixtime, glet):
        index = bisect.bisect(self.data, (unixtime, None))
        while index < len(self.data) and self.data[index][0] == unixtime:
            if self.data[index][1] is glet:
                del self.data[index:index + 1]
                return True
            index += 1
        return False

    def dump(self):
        return self.data

class BTreeTimeoutManager(TimeoutManager):
    def __init__(self, data=None, order=BTREE_ORDER):
        self.data = btree.sorted_btree.bulkload(data or [], order)

    def clear(self):
        self.data = btree.sorted_btree(self.data.order)

    def insert(self, unixtime, glet):
        self.data.insert((unixtime, glet))

    def check(self):
        left, right = self.data.split((time.time(), None))
        state.to_run.extend(pair[1] for pair in left)
        self.data = right

    def remove(self, unixtime, glet):
        try:
            self.data.remove((unixtime, glet))
        except ValueError:
            return False
        return True

    def dump(self):
        return list(self.data)

# cooperatively yielded for a set timeout
try:
    import btree
    state.timed_paused = BTreeTimeoutManager()
except ImportError:
    state.timed_paused = BisectingTimeoutManager()


def _hit_poller(timeout):
    events = []
    while 1:
        try:
            events = state.poller.poll(timeout)
            break
        except KeyboardInterrupt, exc:
            # on Ctrl-C, wake up the main without killing the mainloop
            state.to_raise[compat.main_greenlet] = exc
            state.to_run.append(compat.main_greenlet)
            return
        except EnvironmentError, exc:
            if exc.args[0] != errno.EINTR:
                raise

            # interrupted by a signal
            if state.ignore_interrupts:
                events = []
            else:
                state.interrupted = True
                events = [(fd, state.poller.ERRMASK)
                        for fd in state.poller._registry.iterkeys()]
            break

    for fd, eventmap in events:
        readables = []
        writables = []
        removals = []
        callbackpairs = state.descriptormap.get(fd, [])
        for index, (readable, writable) in enumerate(callbackpairs):
            if not readable and not writable:
                removals.append(index)
            else:
                if readable:
                    readables.append(readable)
                if writable:
                    writables.append(writable)

        map(callbackpairs.pop, removals[::-1])
        if not callbackpairs:
            state.descriptormap.pop(fd)

        if eventmap & (state.poller.INMASK | state.poller.ERRMASK):
            for readable in readables:
                readable()
        if eventmap & (state.poller.OUTMASK | state.poller.ERRMASK):
            for writable in writables:
                writable()

    state.to_run.extend(state.awoken_from_events)
    state.awoken_from_events.clear()

    state.timed_paused.check()

    state.to_run.extend(state.paused)
    state.paused = []


class _WeakMethodRef(object):
    def __init__(self, method):
        if getattr(method, "im_self", None):
            self.obj = weakref.ref(method.im_self)
        elif getattr(method, "im_class", None):
            self.obj = weakref.ref(method.im_class)
        else:
            self.obj = None

        if getattr(method, "im_func", None):
            method = method.im_func
        self.func = weakref.ref(method)

    def __nonzero__(self):
        if self.obj is not None and not self.obj():
            return False
        return self.func() is not None

    def __call__(self, *args, **kwargs):
        if not self:
            return None
        if self.obj is not None:
            args = (self.obj(),) + args
        return self.func()(*args, **kwargs)


def _register_fd(fd, readable, writable):
    # accepts callback functions for readable and writable events
    if readable is not None:
        readable = _WeakMethodRef(readable)
    if writable is not None:
        writable = _WeakMethodRef(writable)
    state.descriptormap[fd].append((readable, writable))


def greenlet(func, args=(), kwargs=None):
    """create a new greenlet from a function and arguments

    :param func: the function the new greenlet should run
    :type func: function
    :param args: any positional arguments for the function
    :type args: tuple
    :param kwargs: any keyword arguments for the function
    :type kwargs: dict or None

    the only major difference between this function and that of the basic
    greenlet api is that this one sets the new greenlet's parent to be the
    greenhouse main loop greenlet, which is a requirement for greenlets that
    will wind up in the greenhouse scheduler.
    """
    if args or kwargs:
        def target():
            return func(*args, **(kwargs or {}))
    else:
        target = func
    return compat.greenlet(target, state.mainloop)

def pause():
    "pause and reschedule the current greenlet and switch to the next"
    schedule(compat.getcurrent())
    state.mainloop.switch()

def pause_until(unixtime):
    """pause and reschedule the current greenlet until a set time

    :param unixtime: the unix timestamp of when to bring this greenlet back
    :type unixtime: int or float
    """
    schedule_at(unixtime, compat.getcurrent())
    state.mainloop.switch()

def pause_for(secs):
    """pause and reschedule the current greenlet for a set number of seconds

    :param secs: number of seconds to pause
    :type secs: int or float
    """
    pause_until(time.time() + secs)

def schedule(target=None, args=(), kwargs=None):
    """insert a greenlet into the scheduler

    If provided a function, it is wrapped in a new greenlet

    :param target: what to schedule
    :type target: function or greenlet
    :param args:
        arguments for the function (only used if ``target`` is a function)
    :type args: tuple
    :param kwargs:
        keyword arguments for the function (only used if ``target`` is a
        function)
    :type kwargs: dict or None

    :returns: the ``target`` argument

    This function can also be used as a decorator, either preloading ``args``
    and/or ``kwargs`` or not:

    >>> @schedule
    >>> def f():
    ...     print 'hello from f'

    >>> @schedule(args=('world',))
    >>> def f(name):
    ...     print 'hello %s' % name
    """
    if target is None:
        def decorator(target):
            return schedule(target, args=args, kwargs=kwargs)
        return decorator
    if isinstance(target, compat.greenlet) or target is compat.main_greenlet:
        glet = target
    else:
        glet = greenlet(target, args, kwargs)
    state.paused.append(glet)
    return target

def schedule_at(unixtime, target=None, args=(), kwargs=None):
    """insert a greenlet into the scheduler to be run at a set time

    If provided a function, it is wrapped in a new greenlet

    :param unixtime:
        the unix timestamp at which the new greenlet should be started
    :type unixtime: int or float
    :param target: what to schedule
    :type target: function or greenlet
    :param args:
        arguments for the function (only used if ``target`` is a function)
    :type args: tuple
    :param kwargs:
        keyword arguments for the function (only used if ``target`` is a
        function)
    :type kwargs: dict or None

    :returns: the ``target`` argument

    This function can also be used as a decorator:

    >>> @schedule_at(1296423834)
    >>> def f():
    ...     print 'hello from f'

    and args/kwargs can also be preloaded:

    >>> @schedule_at(1296423834, args=('world',))
    >>> def f(name):
    ...     print 'hello %s' % name
    """
    if target is None:
        def decorator(target):
            return schedule_at(unixtime, target, args=args, kwargs=kwargs)
        return decorator
    if isinstance(target, compat.greenlet) or target is compat.main_greenlet:
        glet = target
    else:
        glet = greenlet(target, args, kwargs)
    state.timed_paused.insert(unixtime, glet)
    return target

def schedule_in(secs, target=None, args=(), kwargs=None):
    """insert a greenlet into the scheduler to run after a set time

    If provided a function, it is wrapped in a new greenlet

    :param secs: the number of seconds to wait before running the target
    :type unixtime: int or float
    :param target: what to schedule
    :type target: function or greenlet
    :param args:
        arguments for the function (only used if ``target`` is a function)
    :type args: tuple
    :param kwargs:
        keyword arguments for the function (only used if ``target`` is a
        function)
    :type kwargs: dict or None

    :returns: the ``target`` argument

    This function can also be used as a decorator:

    >>> @schedule_in(30)
    >>> def f():
    ...     print 'hello from f'

    and args/kwargs can also be preloaded:

    >>> @schedule_in(30, args=('world',))
    >>> def f(name):
    ...     print 'hello %s' % name
    """
    return schedule_at(time.time() + secs, target, args, kwargs)

def schedule_recurring(interval, target=None, maxtimes=0, starting_at=0,
        args=(), kwargs=None):
    """insert a greenlet into the scheduler to run regularly at an interval

    If provided a function, it is wrapped in a new greenlet

    :param interval: the number of seconds between invocations
    :type interval: int or float
    :param target: what to schedule
    :type target: function or greenlet
    :param maxtimes: if provided, do not run more than ``maxtimes`` iterations
    :type maxtimes: int
    :param starting_at:
        the unix timestamp of when to schedule it for the first time (defaults
        to the time of the ``schedule_recurring`` call)
    :type starting_at: int or float
    :param args: arguments for the function
    :type args: tuple
    :param kwargs: keyword arguments for the function
    :type kwargs: dict or None

    :returns: the ``target`` argument

    This function can also be used as a decorator:

    >>> @schedule_recurring(30)
    >>> def f():
    ...     print "the regular 'hello' from f"

    and args/kwargs can also be preloaded:

    >>> @schedule_recurring(30, args=('world',))
    >>> def f(name):
    ...     print 'the regular hello %s' % name
    """
    starting_at = starting_at or time.time()

    if target is None:
        def decorator(target):
            return schedule_recurring(
                    interval, target, maxtimes, starting_at, args, kwargs)
        return decorator

    func = target
    if isinstance(target, compat.greenlet) or target is compat.main_greenlet:
        if target.dead:
            raise TypeError("can't schedule a dead greenlet")
        func = target.run

    def run_and_schedule_one(tstamp, count):
        # pass in the time scheduled instead of just checking
        # time.time() so that delays don't add up
        if not maxtimes or count < maxtimes:
            tstamp += interval
            func(*args, **(kwargs or {}))
            schedule_at(tstamp, run_and_schedule_one,
                    args=(tstamp, count + 1))

    firstrun = starting_at + interval
    schedule_at(firstrun, run_and_schedule_one, args=(firstrun, 0))

    return target

def schedule_exception(exception, target):
    """schedule a greenlet to have an exception raised in it immediately

    :param exception: the exception to raise in the greenlet
    :type exception: Exception
    :param target: the greenlet that should receive the exception
    :type target: greenlet
    """
    if not isinstance(target, compat.greenlet):
        raise TypeError("can only schedule exceptions for greenlets")
    if target.dead:
        raise ValueError("can't send exceptions to a dead greenlet")
    schedule(target)
    state.to_raise[target] = exception

def schedule_exception_at(unixtime, exception, target):
    """schedule a greenlet to have an exception raised at a unix timestamp

    :param unixtime: when to raise the exception in the target
    :type unixtime: int or float
    :param exception: the exception to raise in the greenlet
    :type exception: Exception
    :param target: the greenlet that should receive the exception
    :type target: greenlet
    """
    if not isinstance(target, compat.greenlet):
        raise TypeError("can only schedule exceptions for greenlets")
    if target.dead:
        raise ValueError("can't send exceptions to a dead greenlet")
    schedule_at(unixtime, target)
    state.to_raise[target] = exception

def schedule_exception_in(secs, exception, target):
    """schedule a greenlet receive an exception after a number of seconds

    :param secs: the number of seconds to wait before raising
    :type secs: int or float
    :param exception: the exception to raise in the greenlet
    :type exception: Exception
    :param target: the greenlet that should receive the exception
    :type target: greenlet
    """
    schedule_exception_at(time.time() + secs, exception, target)

def end(target):
    """schedule a greenlet to be stopped immediately

    :param target: the greenlet to end
    :type target: greenlet
    """
    if not isinstance(target, compat.greenlet):
        raise TypeError("argument must be a greenlet")
    if not target.dead:
        schedule(target)
        state.to_raise[target] = compat.GreenletExit()

def _remove_from_timedout(waketime, glet):
    if state.timed_paused.remove(waketime, glet):
        return True

    try:
        state.to_run.remove(glet)
    except ValueError:
        return False
    return True


@compat.greenlet
def mainloop():
    target = None
    while 1:
        # python shutdown
        if not (sys and state):
            break

        state.interrupted = False

        if not state.to_run:
            _hit_poller(0)

        while not state.to_run:
            # if there are timed-paused greenlets, we can
            # just wait until the first of them wakes up
            if state.timed_paused:
                until = state.timed_paused.first()[0] + 0.001
                _hit_poller(until - time.time())
            else:
                _hit_poller(None)

        prev = target
        target = state.to_run.popleft()

        # global trace hooks
        if state.global_hooks:
            _run_global_hooks(prev, target)

        # local trace incoming hooks
        if target in state.local_to_hooks:
            _run_local_hooks(
                    target, state.local_to_hooks[target], True)

        try:
            # pick up any exception we are supposed to throw in
            if target in state.to_raise:
                target.throw(state.to_raise.pop(target))
            else:
                target.switch()
        except Exception:
            # python shutdown
            if not (sys and state):
                break
            klass, exc, tb = sys.exc_info()
            handle_exception(klass, exc, tb, coro=target)
            del klass, exc, tb

        # local trace outgoing hooks
        if target in state.local_from_hooks:
            _run_local_hooks(
                    target, state.local_from_hooks[target], False)

state.mainloop = mainloop

def _run_local_hooks(target, hooks, incoming):
    replacement_hooks = []
    direction = 1 if incoming else 2
    for weak in hooks:
        func = weak()
        if func is None:
            continue

        try:
            func(direction, target)
        except Exception:
            continue

        replacement_hooks.append(weak)

    hooks[:] = replacement_hooks

def _run_global_hooks(coming_from, going_to):
    replacement_hooks = []
    for weak in state.global_hooks:
        func = weak()
        if func is None:
            continue

        try:
            func(coming_from, going_to)
        except Exception:
            continue

        replacement_hooks.append(weak)

    state.global_hooks[:] = replacement_hooks


def handle_exception(klass, exc, tb, coro=None):
    """run all the registered exception handlers

    the first 3 arguments to this function match the output of
    ``sys.exc_info()``

    :param klass: the exception klass
    :type klass: type
    :param exc: the exception instance
    :type exc: Exception
    :param tb: the traceback object
    :type tb: Traceback
    :param coro:
        behave as though the exception occurred in this coroutine (defaults to
        the current coroutine)
    :type coro: greenlet

    exception handlers run would be all those added with
    :func:`global_exception_handler`, and any added for the relevant coroutine
    with :func:`local_exception_handler`.
    """
    if coro is None:
        coro = compat.getcurrent()

    replacement = []
    for weak in state.local_exception_handlers.get(coro, ()):
        func = weak()
        if func is None:
            continue

        try:
            func(klass, exc, tb)
        except Exception:
            continue

        replacement.append(weak)

    if replacement:
        state.local_exception_handlers[coro][:] = replacement

    replacement = []
    for weak in state.global_exception_handlers:
        func = weak()
        if func is None:
            continue

        try:
            func(klass, exc, tb)
        except Exception:
            continue

        replacement.append(weak)

    state.global_exception_handlers[:] = replacement

def global_exception_handler(handler):
    """add a callback for when an exception goes uncaught in any greenlet

    :param handler:
        the callback function. must be a function taking 3 arguments:

        - ``klass`` the exception class
        - ``exc`` the exception instance
        - ``tb`` the traceback object
    :type handler: function

    Note also that the callback is only held by a weakref, so if all other refs
    to the function are lost it will stop handling greenlets' exceptions
    """
    if not hasattr(handler, "__call__"):
        raise TypeError("exception handlers must be callable")

    state.global_exception_handlers.append(weakref.ref(handler))

    return handler

def remove_global_exception_handler(handler):
    """remove a callback from the list of global exception handlers

    :param handler:
        the callback, previously added via :func:`global_exception_handler`,
        to remove
    :type handler: function

    :returns: bool, whether the handler was found (and therefore removed)
    """
    for i, cb in enumerate(state.global_exception_handlers):
        cb = cb()
        if cb is not None and cb is handler:
            state.global_exception_handlers.pop(i)
            return True
    return False

def local_exception_handler(handler=None, coro=None):
    """add a callback for when an exception occurs in a particular greenlet

    :param handler:
        the callback function, must be a function taking 3 arguments:

        - ``klass`` the exception class
        - ``exc`` the exception instance
        - ``tb`` the traceback object
    :type handler: function
    :param coro:
        the coroutine for which to apply the exception handler (defaults to the
        current coroutine)
    :type coro: greenlet
    """
    if handler is None:
        return lambda h: local_exception_handler(h, coro)

    if not hasattr(handler, "__call__"):
        raise TypeError("exception handlers must be callable")

    if coro is None:
        coro = compat.getcurrent()

    state.local_exception_handlers.setdefault(coro, []).append(
            weakref.ref(handler))

    return handler

def remove_local_exception_handler(handler, coro=None):
    """remove a callback from the list of exception handlers for a coroutine

    :param handler: the callback to remove
    :type handler: function
    :param coro: the coroutine for which to remove the local handler
    :type coro: greenlet

    :returns: bool, whether the handler was found (and therefore removed)
    """
    if coro is None:
        coro = compat.getcurrent()

    for i, cb in enumerate(state.local_exception_handlers.get(coro, [])):
        cb = cb()
        if cb is not None and cb is handler:
            state.local_exception_handlers[coro].pop(i)
            return True
    return False


def global_hook(handler):
    """add a callback to run in every switch between coroutines

    :param handler:
        the callback function, must be a function taking 2 arguments:

        - the greenlet being switched from
        - the greenlet being switched to

        be aware that only a weak reference to this function will be held.
    :type handler: function
    """
    if not hasattr(handler, "__call__"):
        raise TypeError("trace hooks must be callable")

    state.global_hooks.append(weakref.ref(handler))

    return handler

def remove_global_hook(handler):
    """remove a callback from the list of global hooks

    :param handler:
        the callback function, previously added with global_hook, to remove
        from the list of global hooks
    :type handler: function

    :returns: bool, whether the handler was removed from the global hooks
    """
    for i, cb in enumerate(state.global_hooks):
        cb = cb()
        if cb is not None and cb is handler:
            state.global_hooks.pop(i)
            return True
    return False


def local_incoming_hook(handler=None, coro=None):
    """add a callback to run every time a greenlet is about to be switched to

    :param handler:
        the callback function, must be a function taking 2 arguments:

        - an integer indicating whether it is being called as an incoming (1)
          hook or an outgoing (2) hook (in this case it will always receive 1).
        - the coroutine being switched into (in this case it will always be the
          same as the one indicated by the ``coro`` argument to
          ``local_incoming_hook``.

        Be aware that only a weak reference to this function will be held.
    :type handler: function
    :param coro:
        the coroutine for which to apply the trace hook (defaults to current)
    :type coro: greenlet
    """
    if handler is None:
        return lambda h: local_incoming_hook(h, coro)

    if not hasattr(handler, "__call__"):
        raise TypeError("trace hooks must be callable")

    if coro is None:
        coro = compat.getcurrent()

    state.local_to_hooks.setdefault(coro, []).append(
            weakref.ref(handler))

    return handler

def remove_local_incoming_hook(handler, coro=None):
    """remove a callback from the incoming hooks for a particular coro

    :param handler: the callback previously added via local_incoming_hook
    :type handler: function
    :param coro: the coroutine for which the hook should be removed
    :type coro: greenlet

    :returns: bool, whether the handler was found and removed
    """
    if coro is None:
        coro = compat.getcurrent()

    for i, cb in enumerate(state.local_to_hooks.get(coro, [])):
        cb = cb()
        if cb is not None and cb is handler:
            state.local_to_hooks[coro].pop(i)
            return True
    return False

def local_outgoing_hook(handler=None, coro=None):
    """add a callback to run every time a greenlet is switched away from

    :param handler:
        the callback function, must be a function taking 2 arguments:

        - an integer indicating whether it is being called as an incoming (1)
          hook or as an outgoing (2) hook (in this case it will always be 2).
        - the coroutine being switched from (in this case it is the one
          indicated by the ``coro`` argument to ``local_outgoing_hook``.

        Be aware that only a weak reference to this function will be held.
    :type handler: function
    :param coro:
        the coroutine for which to apply the trace hook (defaults to current)
    :type coro: greenlet
    """
    if handler is None:
        return lambda h: local_outgoing_hook(h, coro)

    if not hasattr(handler, "__call__"):
        raise TypeError("trace hooks must be callable")

    if coro is None:
        coro = compat.getcurrent()

    state.local_from_hooks.setdefault(coro, []).append(
            weakref.ref(handler))

    return handler

def remove_local_outgoing_hook(handler, coro=None):
    """remove a callback from the outgoing hooks for a particular coro

    :param handler: the callback previously added via local_outgoing_hook
    :type handler: function
    :param coro: the coroutine for which the hook should be removed
    :type coro: greenlet

    :returns: bool, whether the handler was found and removed
    """
    if coro is None:
        coro = compat.getcurrent()

    for i, cb in enumerate(state.local_from_hooks.get(coro, [])):
        cb = cb()
        if cb is not None and cb is handler:
            state.local_from_hooks[coro].pop(i)
            return True
    return False

def set_ignore_interrupts(flag=True):
    """turn off EINTR-raising from emulated syscalls on interruption by signals

    due to the nature of greenhouse's system call emulation,
    ``signal.siginterrupt`` can't be made to work with it. specifically,
    greenhouse can't differentiate between different signals. so this function
    toggles whether to restart for *ALL* or *NO* signals.

    :param flag:
        whether to turn EINTR exceptions off (``True``) or on (``False``)
    :type flag: bool
    """
    state.ignore_interrupts = bool(flag)

def reset_poller(poll=None):
    """replace the scheduler's poller, throwing away any pre-existing state

    this is only really a good idea in the new child process after a fork(2).
    """
    state.poller = poll or poller.best()
