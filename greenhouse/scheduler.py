import bisect
import operator
import sys
import threading
import time
import traceback

from greenhouse._state import state
from greenhouse.compat import greenlet


__all__ = ["get_next", "pause", "pause_until", "pause_for", "schedule",
           "schedule_at", "schedule_in", "schedule_recurring"]

# this is intended to be monkey-patchable from client code
PRINT_EXCEPTIONS = True

# pause 5ms when there are no greenlets to run
NOTHING_TO_DO_PAUSE = 0.005

def _socketpoll():
    if not hasattr(state, 'poller'):
        import greenhouse.poller #pragma: no cover
    events = state.poller.poll()
    for fd, eventmap in events:
        socks = []
        for index, weakref in enumerate(state.descriptormap[fd]):
            sock = weakref()
            if sock is None or sock._closed:
                state.descriptormap[fd].pop(index)
            else:
                socks.append(sock)
        if eventmap & state.poller.INMASK:
            for sock in socks:
                sock._readable.set()
                sock._readable.clear()
        if eventmap & state.poller.OUTMASK:
            for sock in socks:
                sock._writable.set()
                sock._writable.clear()
    return events

def _find_awoken():
    state.to_run.extend(state.awoken_from_events)
    state.awoken_from_events.clear()

def _find_timein():
    index = bisect.bisect(state.timed_paused, (time.time(), None))
    state.to_run.extend(p[1] for p in state.timed_paused[:index])
    state.timed_paused = state.timed_paused[index:]

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

        # wait for timeouts and events while we don't have anything to run
        while not state.to_run:
            time.sleep(NOTHING_TO_DO_PAUSE)
            _socketpoll()
            _find_awoken()
            _find_timein()

    return state.to_run.popleft()

def pause():
    'pause and reschedule the current greenlet and switch to the next'
    schedule(greenlet.getcurrent())
    get_next().switch()

def pause_until(unixtime):
    '''pause and reschedule the current greenlet until a set time,
    then switch to the next'''
    schedule_at(unixtime, greenlet.getcurrent())
    get_next().switch()

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
    if isinstance(target, greenlet):
        glet = target
    else:
        if args or kwargs:
            inner_target = target
            def target():
                inner_target(*args, **(kwargs or {}))
        if not hasattr(state, "generic_parent"):
            build_generic_parent()
        glet = greenlet(target, state.generic_parent)
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
        if not hasattr(state, "generic_parent"):
            build_generic_parent()
        glet = greenlet(target, state.generic_parent)
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

def build_generic_parent():
    @greenlet
    def generic_parent(ended):
        while 1:
            if not traceback: #pragma: no cover
                # python's shutdown sequence gets out of wack when we have
                # greenlets in play. in certain circumstances, the traceback
                # module becomes None before this code runs.
                break
            try:
                get_next().switch()
            except Exception, exc:
                if PRINT_EXCEPTIONS: #pragma: no cover
                    traceback.print_exception(*sys.exc_info(), file=sys.stderr)
    state.generic_parent = generic_parent

    # rig it so the next get_next() call will definitely put us right back here
    state.to_run.appendleft(greenlet.getcurrent())

    # then prime the pump. if there is a traceback before the generic parent
    # has a chance to get into its 'try' block, the generic parent will die of
    # that traceback and it will wind up being raised in the main greenlet
    @schedule
    def f():
        pass
    get_next().switch()

build_generic_parent()

def hybridize():
    '''change the process-global scheduler state to be thread-local

    this allows multiple OS-threads to each have their own schedulers with
    multiple greenlets in them.

    it is only allowed if there is just one thread currently running. all
    greenlets running will be assigned to the scheduler for the main thread,
    but from this point on new greenlets will go into the scheduler for the
    currently-running thread. it is not possible to move a greenlet to a
    different thread.

    there is no reverse operation.
    '''
    assert threading.active_count() == 1, "multiple threads are already active"
    import greenhouse._state as state

    procstate, state.state = state.state, threading.local()

    state.state.awoken_from_events = procstate.awoken_from_events
    state.state.timed_paused = procstate.timed_paused
    state.state.paused = procstate.paused
    state.state.descriptormap = procstate.descriptormap
    state.state.to_run = procstate.to_run
    state.state.generic_parent = procstate.generic_parent
