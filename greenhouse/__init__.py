from greenhouse.compat import *
from greenhouse.utils import *
from greenhouse.scheduler import *
from greenhouse.pool import *
from greenhouse.io import *
from greenhouse._state import *


def show_state():
    print "%d greenlets awoken from events, waiting for their turn" \
            % len(state.awoken_from_events)
    print "%d greenlets waiting on %d events" % (
            sum(map(len, state.paused_on_events.values())),
            len(state.paused_on_events.keys()))
    print "%d greenlets waiting for timestamps" % len(state.timed_paused)
    print "%d greenlets cooperatively yielded, waiting for their turn" \
            % len(state.paused)
