import collections


# maps events to a list of coros waiting on them
paused_on_events = collections.defaultdict(collections.deque)

# from events that have triggered
awoken_from_events = set()

# cooperatively yielded for a set timeout
timed_paused = []

# executed a simple cooperative yield
paused = collections.deque()

# map of file numbers to the sockets on that descriptor
sockets = collections.defaultdict(list)

# lined up to run right away
to_run = collections.deque()
