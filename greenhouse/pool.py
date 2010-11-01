from __future__ import with_statement

import sys

from greenhouse import compat, scheduler, utils


__all__ = ["OneWayPool", "Pool", "OrderedPool", "map"]

_STOP = object()


class OneWayPool(object):
    def __init__(self, func, size=10):
        self.func = func
        self.size = size
        self.inq = utils.Queue()
        self.closed = False

    def start(self):
        for i in xrange(self.size):
            scheduler.schedule(self._runner)
        self.closed = False

    def close(self):
        self.closed = True
        for i in xrange(self.size):
            self.inq.put(_STOP)

    __del__ = close

    def _runner(self):
        while 1:
            input = self.inq.get()
            if input is _STOP:
                break
            self._handle_one(input)
            self.inq.task_done()

    def _handle_one(self, input):
        self.run_func(*input)

    def run_func(self, args, kwargs):
        try:
            return self.func(*args, **kwargs), True
        except Exception:
            klass, exc, tb = sys.exc_info()
            return (klass, exc, tb), False

    def put(self, *args, **kwargs):
        self.inq.put((args, kwargs))

    def join(self):
        self.inq.join()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, klass, value, tb):
        self.close()


class Pool(OneWayPool):
    def __init__(self, *args, **kwargs):
        super(Pool, self).__init__(*args, **kwargs)
        self.outq = utils.Queue()

    def _handle_one(self, input):
        self.outq.put(self.run_func(*input))

    def get(self):
        if self.closed:
            raise RuntimeError("the pool is closed")

        result, succeeded = self.outq.get()
        if not succeeded:
            klass, exc, tb = result
            raise klass, exc, tb
        return result

    def close(self):
        super(Pool, self).close()
        for waiter in self.outq._waiters:
            scheduler.schedule_exception(
                    RuntimeError("the pool has been closed"), waiter)


class OrderedPool(Pool):
    def __init__(self, func, size=10):
        super(OrderedPool, self).__init__(func, size)
        self._putcount = 0
        self._getcount = 0
        self._cache = {}

    def _handle_one(self, input):
        count, input = input
        self.outq.put((count, self.run_func(*input)))

    def put(self, *args, **kwargs):
        self.inq.put((self._putcount, (args, kwargs)))
        self._putcount += 1

    def get(self):
        if self.closed:
            raise RuntimeError("the pool is closed")

        while self._getcount not in self._cache:
            counter, result = self.outq.get()
            self._cache[counter] = result

        result, succeeded = self._cache.pop(self._getcount)
        self._getcount += 1

        if not succeeded:
            klass, exc, tb = result
            raise klass, exc, tb
        return result


def map(func, items, pool_size=10):
    with OrderedPool(func, pool_size) as op:
        for item in items:
            op.put(item)

        for item in items:
            yield op.get()
