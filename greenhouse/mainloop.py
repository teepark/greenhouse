import bisect
import time

from greenhouse import _state
from greenhouse.compat import greenlet


POLL_TIMEOUT = 0.1
NOTHING_TO_DO_PAUSE = 0.05
LAST_SELECT = 0

def get_next():
    'figure out the next greenlet to run'
    if _state.awoken_from_events:
        return _state.awoken_from_events.pop()

    now = time.time()
    if now >= LAST_SELECT + POLL_TIMEOUT:
        _socketpoll()

    if _state.awoken_from_events:
        return _state.awoken_from_events.pop()

    if _state.timed_paused and now >= _state.timed_paused[0][0]:
        return _state.timed_paused.pop(0)[1]

    return (_state.paused and (_state.paused.popleft(),) or (None,))[0]

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
    if not isinstance(target, greenlet):
        if args or kwargs:
            inner_target = target
            def target():
                inner_target(*args, **kwargs)
        glet = greenlet(target, generic_parent)
    else:
        glet = target
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
    if not isinstance(target, greenlet):
        if args or kwargs:
            inner_target = target
            def target():
                inner_target(*args, **kwargs)
        glet = greenlet(target, generic_parent)
    else:
        glet = target
    bisect.insort(_state.timed_paused, (unixtime, glet))
    return target

def schedule_in(secs, run=None, args=(), kwargs=None):
    '''set up a greenlet or function to run in the specified number of seconds

    if *run* is a function, it is wrapped in a new greenlet. the greenlet will
    be run sometime after *secs* seconds have passed'''
    return schedule_at(time.time() + secs, run, args, kwargs)

@greenlet
def generic_parent(ended):
    while 1:
        go_to_next()

def _socketpoll():
    if not hasattr(_state, 'poller'):
        import greenhouse.poller
    events = _state.poller.poll()
    for fd, eventmap in events:
        socks = _state.sockets[fd]
        if eventmap & _state.poller.INMASK:
            if socks:
                socks[0]._readable.set()
                socks[0]._readable.clear()
        if eventmap & _state.poller.OUTMASK:
            if socks:
                socks[0]._writable.set()
                socks[0]._writable.clear()
