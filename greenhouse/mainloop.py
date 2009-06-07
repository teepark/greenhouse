import bisect
import operator
import time

from greenhouse import _state
from greenhouse.compat import greenlet


POLL_TIMEOUT = 0.01
NOTHING_TO_DO_PAUSE = 0.005
LAST_SELECT = 0

def get_next():
    'figure out the next greenlet to run'
    if not _state.to_run:
        # run the socket poller to trigger network events
        _socketpoll()

        # start with events that have already triggered
        _state.to_run.extend(_state.awoken_from_events)
        _state.awoken_from_events.clear()

        # append timed pauses that have expired
        index = bisect.bisect(_state.timed_paused, (time.time(), None))
        _state.to_run.extend(_state.timed_paused[:index])
        _state.timed_paused = _state.timed_paused[index:]

        # append simple cooperative yields
        _state.to_run.extend(_state.paused)
        _state.paused = []

        # loop waiting for network events while we don't have anything to run
        if not _state.to_run:
            while not _state.awoken_from_events:
                time.sleep(NOTHING_TO_DO_PAUSE)
                _socketpoll()
            _state.to_run.extend(_state.awoken_from_events)
            _state.awoken_from_events.clear()

    return _state.to_run.popleft()

def go_to_next():
    '''pause the current greenlet and switch to the next

    this is different from the pause* methods in that it does not
    reschedule the current greenlet'''
    next = get_next()
    while next is None:
        time.sleep(NOTHING_TO_DO_PAUSE)
        next = get_next()
    next.switch()

def pause():
    'pause and reschedule the current greenlet and switch to the next'
    schedule(greenlet.getcurrent())
    go_to_next()

def pause_until(unixtime):
    '''pause and reschedule the current greenlet until a set time,
    then switch to the next'''
    schedule_at(unixtime, greenlet.getcurrent())
    go_to_next()

def pause_for(secs):
    '''pause and reschedule the current greenlet for a set number of seconds,
    then switch to the next'''
    pause_until(time.time() + secs)

def schedule(target=None, args=(), kwargs=None):
    '''set up a greenlet or function to run later

    if *target* is a function, it is wrapped in a new greenlet. the greenlet
    will be run at an undetermined time. also usable as a decorator'''
    kwargs = kwargs or {}
    if target is None:
        def decorator(target):
            return schedule(target, args=args, kwargs=kwargs)
        return decorator
    if isinstance(target, greenlet):
        glet = target
    else:
        if args or kwargs:
            inner_target = target
            def target():
                inner_target(*args, **kwargs)
        glet = greenlet(target, generic_parent)
    _state.paused.append(glet)
    return target

def schedule_at(unixtime, target=None, args=(), kwargs=None):
    '''set up a greenlet or function to run at the specified timestamp

    if *target* is a function, it is wrapped in a new greenlet. the greenlet
    will be run sometime after *unixtime*, a timestamp'''
    kwargs = kwargs or {}
    if target is None:
        def decorator(target):
            return schedule_at(unixtime, target, args=args, kwargs=kwargs)
        return decorator
    if isinstance(target, greenlet):
        glet = target
    else:
        if args or kwargs:
            inner_target = target
            def target():
                inner_target(*args, **kwargs)
        glet = greenlet(target, generic_parent)
    bisect.insort(_state.timed_paused, (unixtime, glet))
    return target

def schedule_in(secs, target=None, args=(), kwargs=None):
    '''set up a greenlet or function to run in the specified number of seconds

    if *target* is a function, it is wrapped in a new greenlet. the greenlet
    will be run sometime after *secs* seconds have passed'''
    return schedule_at(time.time() + secs, target, args, kwargs)

@greenlet
def generic_parent(ended):
    while 1:
        go_to_next()

def _socketpoll():
    global LAST_SELECT
    if not hasattr(_state, 'poller'):
        import greenhouse.poller
    events = _state.poller.poll()
    for fd, eventmap in events:
        socks = filter(None, map(operator.methodcaller("__call__"),
                _state.sockets[fd]))
        if eventmap & _state.poller.INMASK:
            for sock in socks:
                sock._readable.set()
                sock._readable.clear()
        if eventmap & _state.poller.OUTMASK:
            for sock in socks:
                sock._writable.set()
                sock._writable.clear()
    LAST_SELECT = time.time()
    return events
