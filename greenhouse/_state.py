import collections
import threading

state = threading.local()

# maps events to a list of coros waiting on them
state.paused_on_events = collections.defaultdict(collections.deque)

# from events that have triggered
state.awoken_from_events = set()

# cooperatively yielded for a set timeout
state.timed_paused = []

# executed a simple cooperative yield
state.paused = collections.deque()

# map of file numbers to the sockets on that descriptor
state.sockets = collections.defaultdict(list)

# lined up to run right away
state.to_run = collections.deque()
