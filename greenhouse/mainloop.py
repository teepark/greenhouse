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

def pause_for(secs):
    now = time.time()
    bisect.insort_right(globals.timed_paused, (now + secs, greenlet.getcurrent()))
    go_to_next()

def schedule(func):
    glet = greenlet(func)
    glet.parent = generic_parent
    globals.paused.append(glet)
    return func

@greenlet
def generic_parent(ended):
    while 1:
        next = get_next()
        if next is None:
            time.sleep(0.1)
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
                socks[0]._readable.trigger()
        if eventmap & globals.poller.OUTMASK:
            if socks:
                socks[0]._writable.trigger()
