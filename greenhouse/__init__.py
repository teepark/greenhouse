from greenhouse._state import *
from greenhouse.compat import *
from greenhouse.scheduler import *
from greenhouse.utils import *
from greenhouse.pool import *
from greenhouse.io import *


def show_state(): #pragma: no cover
    print "%d greenlets awoken from events, waiting for their turn" \
            % len(state.awoken_from_events)
    print "%d greenlets waiting for timestamps" % len(state.timed_paused)
    print "%d greenlets cooperatively yielded, waiting for their turn" \
            % len(state.paused)
