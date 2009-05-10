import collections


events = {
    # maps events to a list of coros waiting on them
    'paused': collections.defaultdict(list),

    # from events that have triggered
    'awoken': set()
}

# cooperatively yielded for a set timeout
timed_paused = []

# executed a simple cooperative yield
paused = collections.deque()

# map of file numbers to the sockets on that descriptor
sockets = collections.defaultdict(list)
