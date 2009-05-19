import bisect
import time

from greenhouse import _state
from greenhouse.compat import greenlet


POLL_TIMEOUT = 0.1
NOTHING_TO_DO_PAUSE = 0.05
LAST_SELECT = 0

def get_next():
    'figure out the next greenlet to run'
    global LAST_SELECT

    if _state.events['awoken']:
        return _state.events['awoken'].pop()

    now = time.time()
    if now >= LAST_SELECT + POLL_TIMEOUT:
        LAST_SELECT = now
        _socketpoll()

    if _state.events['awoken']:
        return _state.events['awoken'].pop()

    if _state.timed_paused and now >= _state.timed_paused[0][0]:
        return _state.timed_paused.pop()[1]

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
    schedule_in(secs, greenlet.getcurrent())
    go_to_next()

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
            @greenlet
            def target():
                inner_target(*args, **kwargs)
        else:
            target = greenlet(target)
    target.parent = generic_parent
    _state.paused.append(target)
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
            @greenlet
            def target():
                inner_target(*args, **kwargs)
        else:
            target = greenlet(target)
    target.parent = generic_parent
    bisect.insort(_state.timed_paused, (unixtime, target))
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
            for sock in socks:
                sock._readable.set()
                sock._readable.clear()
        if eventmap & _state.poller.OUTMASK:
            for sock in socks:
                sock._writable.set()
                sock._writable.clear()
