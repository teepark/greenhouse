import bisect
import time

from greenhouse import _state
from greenhouse.compat import greenlet


POLL_TIMEOUT = 0.1
NOTHING_TO_DO_PAUSE = 0.05
LAST_SELECT = 0

def get_next():
    global LAST_SELECT

    if _state.events['awoken']:
        return _state.events['awoken'].pop()
    
    now = time.time()
    if now >= LAST_SELECT + POLL_TIMEOUT:
        LAST_SELECT = now
        socketpoll()

    if _state.events['awoken']:
        return _state.events['awoken'].pop()

    if _state.timed_paused and now >= _state.timed_paused[0][0]:
        return _state.timed_paused.pop()[1]

    return (_state.paused and (_state.paused.popleft(),) or (None,))[0]

def go_to_next():
    next = get_next()
    while next is None:
        time.sleep(NOTHING_TO_DO_PAUSE)
        next = get_next()
    next.switch()

def pause():
    _state.paused.append(greenlet.getcurrent())
    go_to_next()

def pause_until(unixtime):
    bisect.insort(_state.timed_paused, (unixtime, greenlet.getcurrent()))
    go_to_next()

def pause_for(secs):
    pause_until(time.time() + secs)

def schedule(run):
    glet = isinstance(run, greenlet) and run or greenlet(run)
    glet.parent = generic_parent
    _state.paused.append(glet)
    return run

def schedule_at(unixtime, run=None):
    if run is None:
        def decorator(run):
            glet = isinstance(run, greenlet) and run or greenlet(run)
            bisect.insort(_state.timed_paused, (unixtime, glet))
            return run
        return decorator
    glet = isinstance(run, greenlet) and run or greenlet(run)
    bisect.insort(_state.timed_paused, (unixtime, glet))
    return run

def schedule_in(secs, run=None):
    return schedule_at(time.time() + secs, run)

@greenlet
def generic_parent(ended):
    while 1:
        next = get_next()
        if next is None:
            time.sleep(NOTHING_TO_DO_PAUSE)
            continue
        ended = next.switch()

def socketpoll():
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
