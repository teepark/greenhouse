from greenhouse.scheduler import schedule
from greenhouse.utils import Queue


__all__ = ["OneWayPool", "Pool", "OrderedPool"]

_STOP = object()


class OneWayPool(object):
    def __init__(self, func, size=10):
        self.func = func
        self.size = size
        self.inq = Queue()

    def start(self):
        for i in xrange(self.size):
            schedule(self._runner)

    def close(self):
        for i in xrange(self.size):
            self.inq.put(_STOP)

    def _runner(self):
        while 1:
            input = self.inq.get()
            if input is _STOP:
                break
            self._handle_one(input)

    def _handle_one(self, input):
        self.func(*(input[0]), **(input[1]))

    def put(self, *args, **kwargs):
        self.inq.put((args, kwargs))

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, klass, value, tb):
        self.close()


class Pool(OneWayPool):
    def __init__(self, *args, **kwargs):
        super(Pool, self).__init__(*args, **kwargs)
        self.outq = Queue()

    def _handle_one(self, input):
        self.outq.put(self.func(*(input[0]), **(input[1])))

    def get(self):
        return self.outq.get()


class OrderedPool(Pool):
    def __init__(self, func, size=10):
        super(OrderedPool, self).__init__(func, size)
        self._putcount = 0
        self._getcount = 0
        self._cache = {}

    def _handle_one(self, input):
        count, input = input
        self.outq.put((count, self.func(*(input[0]), **(input[1]))))

    def put(self, *args, **kwargs):
        self.inq.put((self._putcount, (args, kwargs)))
        self._putcount += 1

    def get(self):
        while self._getcount not in self._cache:
            counter, result = self.outq.get()
            self._cache[counter] = result
        self._getcount += 1
        return self._cache.pop(self._getcount - 1)


def map(func, items, pool_size=10):
    op = OrderedPool(func, pool_size)
    op.start()
    l = len(items)
    for item in items:
        op.put(item)

    for i in xrange(l):
        yield op.get()
