import bisect
import collections
import errno
import operator
import sys
import time
import weakref

from greenhouse import compat


__all__ = ["pause", "pause_until", "pause_for", "schedule", "schedule_at",
        "schedule_in", "schedule_recurring", "schedule_exception",
        "schedule_exception_at", "schedule_exception_in", "end",
        "add_exception_handler", "handle_exception", "greenlet"]

_exception_handlers = []

POLL_TIMEOUT = 1.0


state = type('GreenhouseState', (), {})()

# from events that have triggered
state.awoken_from_events = set()

# cooperatively yielded for a set timeout
state.timed_paused = []

# executed a simple cooperative yield
state.paused = []

# map of file numbers to the sockets/files on that descriptor
state.descriptormap = collections.defaultdict(list)

# lined up to run right away
state.to_run = collections.deque()

# exceptions queued up for scheduled coros
state.to_raise = weakref.WeakKeyDictionary()


def _hit_poller(timeout, interruption=None):
    interruption = interruption or (lambda: False)
    until = time.time() + timeout
    events = []
    while 1:
        try:
            events = state.poller.poll(timeout)
            break
        except EnvironmentError, exc:
            if exc.args[0] != errno.EINTR:
                raise
            # interrupted by a signal
            if not interruption():
                break
            timeout = until - time.time()

    for fd, eventmap in events:
        socks = []
        objs = state.descriptormap.get(fd, [])
        removals = []
        for index, weak in enumerate(objs):
            sock = weak()
            if sock is None or sock._closed:
                removals.append(index)
            else:
                socks.append(sock)

        map(objs.pop, removals[::-1])
        if not objs:
            state.descriptormap.pop(fd, None)

        if eventmap & (state.poller.INMASK | state.poller.ERRMASK):
            for sock in socks:
                sock._readable.set()
                sock._readable.clear()
        if eventmap & (state.poller.OUTMASK | state.poller.ERRMASK):
            for sock in socks:
                sock._writable.set()
                sock._writable.clear()
    _check_events()

def _check_events():
    state.to_run.extend(state.awoken_from_events)
    state.awoken_from_events.clear()

def _check_paused(skip_simple=False):
    index = bisect.bisect(state.timed_paused, (time.time(), None))
    state.to_run.extend(p[1] for p in state.timed_paused[:index])
    state.timed_paused = state.timed_paused[index:]

    if not skip_simple:
        state.to_run.extend(state.paused)
        state.paused = []

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
    return compat.greenlet(target, mainloop)

def pause():
    "pause and reschedule the current greenlet and switch to the next"
    schedule(compat.getcurrent())
    mainloop.switch()

def pause_until(unixtime):
    """pause and reschedule the current greenlet until a set time

    :param unixtime: the unix timestamp of when to bring this greenlet back
    :type unixtime: int or float
    """
    schedule_at(unixtime, compat.getcurrent())
    mainloop.switch()

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
    if isinstance(target, compat.greenlet):
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
    if isinstance(target, compat.greenlet):
        glet = target
    else:
        glet = greenlet(target, args, kwargs)
    bisect.insort(state.timed_paused, (unixtime, glet))
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
    if isinstance(target, compat.greenlet):
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

def _schedule_to_top(target=None, args=(), kwargs=None):
    if target is None:
        def decorator(target):
            return _schedule_to_top(target, args, kwargs)
        return decorator
    if isinstance(target, compat.greenlet):
        glet = target
    else:
        if args or kwargs:
            inner_target = target
            def target():
                inner_target(*args, **(kwargs or {}))
        glet = compat.greenlet(target, state.mainloop)
    state.to_run.appendleft(glet)
    return target

def _interruption_check():
    _check_events()
    _check_paused()
    return not state.to_run

@compat.greenlet
def mainloop():
    while 1:
        if not sys:
            break
        try:
            if not state.to_run:
                _hit_poller(0)
                _check_paused()

                while not state.to_run:
                    # if there are timed-paused greenlets, we can
                    # just wait until the first of them wakes up
                    if state.timed_paused:
                        until = state.timed_paused[0][0] + 0.001
                        _hit_poller(until - time.time(), _interruption_check)
                        _check_paused()
                    else:
                        _hit_poller(POLL_TIMEOUT, _interruption_check)
                        _check_paused()

            target = state.to_run.popleft()
            exc = state.to_raise.pop(target, None)
            if exc is not None:
                target.throw(exc)
            else:
                target.switch()
        except Exception, exc:
            if sys:
                handle_exception(*sys.exc_info())
state.mainloop = mainloop

def handle_exception(klass, exc, tb):
    """run all the registered exception handlers

    the arguments to this function match the output of ``sys.exc_info()``

    :param klass: the exception klass
    :type klass: type
    :param exc: the exception instance
    :type exc: Exception
    :param tb: the traceback object
    :type tb: Traceback
    """
    global _exception_handlers

    replacement = []
    for weak in _exception_handlers:
        func = weak()
        if func is None:
            continue
        try:
            func(klass, exc, tb)
        except Exception:
            # exceptions from within exception handlers get squashed so as not
            # to create an infinite loop, but we won't be using this handler
            # any more
            continue
        replacement.append(weak)

    _exception_handlers = replacement

def add_exception_handler(handler):
    """add a callback for when an exception goes uncaught in a greenlet

    :param handler:
        the callback function. must be a function taking 3 arguments: ``klass``
        the exception class, ``exc`` the exception instance, and ``tb`` the
        traceback object
    :type handler: function

    Note also that the callback is only held by a weakref, so if all other refs
    to the function are lost it will stop handling greenlets' exceptions
    """
    if not hasattr(handler, "__call__"):
        raise TypeError("exception handlers must be callable")
    _exception_handlers.append(weakref.ref(handler))
