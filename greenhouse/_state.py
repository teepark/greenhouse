import collections
import threading


__all__ = ["state"]

state = threading.local()

# maps events to a list of coros waiting on them
state.paused_on_events = collections.defaultdict(collections.deque)

# from events that have triggered
state.awoken_from_events = set()

# cooperatively yielded for a set timeout
state.timed_paused = []

# executed a simple cooperative yield
state.paused = []

# map of file numbers to the sockets/files on that descriptor
state.descriptormap = collections.defaultdict(list)

# lined up to run right away
state.to_run = collections.deque()
