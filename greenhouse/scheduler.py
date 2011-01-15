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
        "add_exception_handler", "greenlet", "handle_exception"]

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
    if args or kwargs:
        def target():
            return func(*args, **(kwargs or {}))
    else:
        target = func
    return compat.greenlet(target, mainloop)

def pause():
    'pause and reschedule the current greenlet and switch to the next'
    schedule(compat.getcurrent())
    mainloop.switch()

def pause_until(unixtime):
    '''pause and reschedule the current greenlet until a set time,
    then switch to the next'''
    schedule_at(unixtime, compat.getcurrent())
    mainloop.switch()

def pause_for(secs):
    '''pause and reschedule the current greenlet for a set number of seconds,
    then switch to the next'''
    pause_until(time.time() + secs)

def schedule(target=None, args=(), kwargs=None):
    '''set up a greenlet or function to run later

    if *target* is a function, it is wrapped in a new greenlet. the greenlet
    will be run at an undetermined time. also usable as a decorator'''
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
    '''set up a greenlet or function to run at the specified timestamp

    if *target* is a function, it is wrapped in a new greenlet. the greenlet
    will be run sometime after *unixtime*, a timestamp'''
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
    '''set up a greenlet or function to run in the specified number of seconds

    if *target* is a function, it is wrapped in a new greenlet. the greenlet
    will be run sometime after *secs* seconds have passed'''
    return schedule_at(time.time() + secs, target, args, kwargs)

def schedule_recurring(interval, target=None, maxtimes=0, starting_at=0,
        args=(), kwargs=None):
    '''set up a function to run at a regular interval

    every *interval* seconds, *target* will be wrapped in a new greenlet
    and run

    if *maxtimes* is greater than 0, *target* will stop being scheduled after
    *maxtimes* runs

    if *starting_at* is greater than 0, the recurring runs will begin at that
    unix timestamp, instead of ``time.time() + interval``'''
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
    '''set a greenlet to have *exception* raised in it

    *target* must be a greenlet, so unlike schedule(), this can not be a
    decorator'''
    if not isinstance(target, compat.greenlet):
        raise TypeError("can only schedule exceptions for greenlets")
    if target.dead:
        raise ValueError("can't send exceptions to a dead greenlet")
    schedule(target)
    state.to_raise[target] = exception

def schedule_exception_at(unixtime, exception, target):
    '''set a greenlet to have *exception* raised in it at a timestamp

    *target* must be a greenlet. *exception* will be raised in it sometime
    after *unixtime*, a timestamp'''
    if not isinstance(target, compat.greenlet):
        raise TypeError("can only schedule exceptions for greenlets")
    if target.dead:
        raise ValueError("can't send exceptions to a dead greenlet")
    schedule_at(unixtime, target)
    state.to_raise[target] = exception

def schedule_exception_in(secs, exception, target):
    '''set a greenlet have *exception* raised in it *secs* seconds later

    *target* must be a greenlet. *exception* will be raised in it sometime
    after *secs* seconds have elapsed'''
    schedule_exception_at(time.time() + secs, exception, target)

def end(target):
    '''schedule a greenlet to be killed abruptly

    *target* must be a greenlet. it will immediately be scheduled with a
    compat.GreenletExit to be raised in it'''
    schedule_exception(compat.GreenletExit(), target)

def schedule_to_top(target=None, args=(), kwargs=None):
    '''set up a function or greenlet to run, skipping to the front of the line

    if *target* is a function, it is wrapped in a new greenlet. the greenlet
    will be the next greenlet run, unless you call this function again before
    the next blocking action, in which case that one will have skipped to the
    front as well.
    '''
    if target is None:
        def decorator(target):
            return schedule_to_top(target, args, kwargs)
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
                        _check_paused(True)
                    else:
                        _hit_poller(POLL_TIMEOUT, _interruption_check)

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
    "run all registered exception handlers"
    _purge_exception_handlers()

    for weak in _exception_handlers:
        try:
            weak()(klass, exc, tb)
        except Exception:
            # exceptions from within exception handlers get
            # squashed so as not to create an infinite loop
            pass

def _purge_exception_handlers():
    globals()['_exception_handlers'] = [weak for weak in _exception_handlers
            if weak()]

def add_exception_handler(handler):
    if not hasattr(handler, "__call__"):
        raise TypeError("exception handlers must be callable")
    _exception_handlers.append(weakref.ref(handler))
