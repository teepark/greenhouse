from greenhouse.compat import greenlet
from greenhouse.utils import Event, Lock, RLock, Condition, Semaphore,\
        BoundedSemaphore, Timer, Queue, Local
from greenhouse.mainloop import pause, pause_until, pause_for, schedule,\
        schedule_at, schedule_in
from greenhouse.pool import Pool, OrderedPool
from greenhouse.sockets import Socket
from greenhouse import _state


def show_state():
    print "%d greenlets awoken from events, waiting for their turn" \
            % len(_state.awoken_from_events)
    print "%d greenlets waiting on %d events" % (
            sum(map(len, _state.paused_on_events.values())),
            len(_state.paused_on_events.keys()))
    print "%d greenlets waiting for timestamps" % len(_state.timed_paused)
    print "%d greenlets cooperatively yielded, waiting for their turn" \
            % len(_state.paused)
