import bisect
from itertools import imap
import operator
import time

from greenhouse._state import state
from greenhouse.compat import greenlet


# pause 5ms when there are no greenlets to run
NOTHING_TO_DO_PAUSE = 0.005

def _find_timein():
    index = bisect.bisect(state.timed_paused, (time.time(), None))
    newly_timedin = state.timed_paused[:index]
    state.to_run.extend(imap(operator.itemgetter(1), newly_timedin))
    state.timed_paused = state.timed_paused[index:]
    return bool(newly_timedin)

def _find_awoken():
    newly_awoken = bool(state.awoken_from_events)
    state.to_run.extend(state.awoken_from_events)
    state.awoken_from_events.clear()
    return newly_awoken

def get_next():
    'update the scheduler state and figure out the next greenlet to run'
    if not state.to_run:
        # run the socket poller to trigger network events
        _socketpoll()

        # start with events that have already triggered
        _find_awoken()

        # append timed pauses that have expired
        _find_timein()

        # append simple cooperative yields
        state.to_run.extend(state.paused)
        state.paused = []

        # loop waiting for network events while we don't have anything to run
        if not state.to_run:
            while 1:
                time.sleep(NOTHING_TO_DO_PAUSE)
                _socketpoll()
                if _find_awoken() or _find_timein(): break

    return state.to_run.popleft()

def go_to_next():
    '''pause the current greenlet and switch to the next

    this is different from the pause* methods in that it does not
    reschedule the current greenlet'''
    get_next().switch()

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
    state.paused.append(glet)
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
    kwargs = kwargs or {}
    starting_at = starting_at or time.time()

    if target is None:
        def decorator(target):
            return schedule_recurring(interval, target, maxtimes, starting_at,
                                      args, kwargs)
        return decorator

    func = target
    if isinstance(target, greenlet):
        if target.dead:
            raise TypeError("can't schedule a dead greenlet")
        func = target.run

    def run_and_schedule_one(tstamp, count):
        # pass in the time scheduled instead of just checking
        # time.time() so that delays don't add up
        if not maxtimes or count < maxtimes:
            func(*args, **kwargs)
            schedule_at(tstamp, run_and_schedule_one,
                    args=(tstamp + interval, count + 1))

    firstrun = starting_at + interval
    schedule_at(firstrun, run_and_schedule_one, args=(firstrun, 0))

    return target

@greenlet
def generic_parent(ended):
    while 1:
        go_to_next()

def _socketpoll():
    if not hasattr(state, 'poller'):
        import greenhouse.poller
    events = state.poller.poll()
    for fd, eventmap in events:
        socks = filter(None, map(operator.methodcaller("__call__"),
                state.sockets[fd]))
        if eventmap & state.poller.INMASK:
            for sock in socks:
                sock._readable.set()
                sock._readable.clear()
        if eventmap & state.poller.OUTMASK:
            for sock in socks:
                sock._writable.set()
                sock._writable.clear()
    return events
