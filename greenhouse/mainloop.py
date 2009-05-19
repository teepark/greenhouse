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
    bisect.insort(_state.timed_paused, (unixtime, greenlet.getcurrent()))
    go_to_next()

def pause_for(secs):
    '''pause and reschedule the current greenlet for a set number of seconds,
    then switch to the next'''
    pause_until(time.time() + secs)

def schedule(run):
    '''set up a greenlet or function to run later

    if *run* is a function, it is wrapped in a new greenlet. the greenlet will
    be run at an undetermined time. also usable as a decorator'''
    glet = isinstance(run, greenlet) and run or greenlet(run)
    glet.parent = generic_parent
    _state.paused.append(glet)
    return run

def schedule_at(unixtime, run=None):
    '''set up a greenlet or function to run at the specified timestamp

    if *run* is a function, it is wrapped in a new greenlet. the greenlet will
    be run sometime after *unixtime*, a timestamp'''
    if run is None:
        def decorator(run):
            return schedule_at(unixtime, run)
        return decorator
    glet = isinstance(run, greenlet) and run or greenlet(run)
    bisect.insort(_state.timed_paused, (unixtime, glet))
    return run

def schedule_in(secs, run=None):
    '''set up a greenlet or function to run in the specified number of seconds

    if *run* is a function, it is wrapped in a new greenlet. the greenlet will
    be run sometime after *secs* seconds have passed'''
    return schedule_at(time.time() + secs, run)

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
