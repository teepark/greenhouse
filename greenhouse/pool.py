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
        self.coros = []

    def _runner(self):
        while 1:
            input = self.inq.get()
            if input is _STOP:
                break
            self.outq.put(self.func(input))

    def put(self, input):
        self.inq.put(input)

    def get(self):
        return self.outq.get()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, type, value, traceback):
        self.close()

class OrderedPool(Pool):
    def __init__(self, func, size=10):
        def f(pair):
            return pair[0], func(pair[1])

        super(OrderedPool, self).__init__(f, size)

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
