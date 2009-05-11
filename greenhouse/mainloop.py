import bisect
import time

from greenhouse import globals
from greenhouse.compat import greenlet


POLL_TIMEOUT = 0.1
NOTHING_TO_DO_PAUSE = 0.05
last_select = 0

def get_next():
    global last_select

    if globals.events['awoken']:
        return globals.events['awoken'].pop(0)
    
    now = time.time()
    if now >= last_select + POLL_TIMEOUT:
        last_select = now
        socketpoll()

    if globals.events['awoken']:
        return globals.events['awoken'].pop()

    if globals.timed_paused and now >= globals.timed_paused[0][0]:
        return globals.timed_paused.pop()[1]

    return (globals.paused and (globals.paused.popleft(),) or (None,))[0]

def go_to_next():
    next = get_next()
    while next is None:
        time.sleep(NOTHING_TO_DO_PAUSE)
        next = get_next()
    next.switch()

def pause():
    globals.paused.append(greenlet.getcurrent())
    go_to_next()

def pause_until(unixtime):
    bisect.insort_right(globals.timed_paused, (unixtime, greenlet.getcurrent()))
    go_to_next()

def pause_for(secs):
    pause_until(time.time() + secs)

def schedule(func):
    glet = greenlet(func)
    glet.parent = generic_parent
    globals.paused.append(glet)
    return func

def _scheduler(unixtime, func):
    pause_until(unixtime)
    return func()

def schedule_at(unixtime, func=None):
    if func is None:
        def decorator(func):
            schedule(_scheduler(unixtime, func))
            return func
        return decorator
    schedule(_scheduler(unixtime, func))
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
    if not hasattr(globals, 'poller'):
        import greenhouse.poller
    events = globals.poller.poll()
    for fd, eventmap in events:
        socks = globals.sockets[fd]
        if eventmap & globals.poller.INMASK:
            if socks:
                socks[0]._readable.set()
                socks[0]._readable.clear()
        if eventmap & globals.poller.OUTMASK:
            if socks:
                socks[0]._writable.set()
                socks[0]._writable.clear()
