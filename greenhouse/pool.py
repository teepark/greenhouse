import greenhouse.scheduler
from greenhouse.utils import Queue


__all__ = ["Pool", "OrderedPool"]

_STOP = object()

class Pool(object):
    def __init__(self, func, size=10):
        self.func = func
        self.size = size
        self.inq = Queue()
        self.outq = Queue()
        self.coros = []

    def start(self):
        self.coros = []
        for i in xrange(self.size):
            self.coros.append(greenhouse.scheduler.schedule(self._runner))

    def close(self):
        for i in xrange(self.size):
            self.inq.put(_STOP)

    def _runner(self):
        while 1:
            pair = self.inq.get()
            if pair is _STOP:
                break
            self.outq.put((pair[0], self.func(pair[1])))

    def put(self, input):
        self.inq.put((None, input))

    def get(self):
        return self.outq.get()[1]

class OrderedPool(Pool):
    def __init__(self, *args, **kwargs):
        super(OrderedPool, self).__init__(*args, **kwargs)
        self.putcount = 0
        self.getcount = 0
        self.cache = {}

    def put(self, input):
        self.inq.put((self.putcount, input))
        self.putcount += 1

    def get(self):
        while self.getcount not in self.cache:
            pair = self.outq.get()
            self.cache[pair[0]] = pair[1]
        self.getcount += 1
        return self.cache.pop(self.getcount - 1)
