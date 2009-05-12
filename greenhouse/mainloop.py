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

def schedule(func):
    glet = greenlet(func)
    glet.parent = generic_parent
    _state.paused.append(glet)
    return func

def schedule_at(unixtime, func=None):
    if func is None:
        def decorator(func):
            bisect.insort(_state.timed_paused, (unixtime, greenlet(func)))
            return func
        return decorator
    bisect.insort(_state.timed_paused, (unixtime, greenlet(func)))
    return func

def schedule_in(secs, func=None):
    return schedule_at(time.time() + secs, func)

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
