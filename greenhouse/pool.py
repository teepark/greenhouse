from __future__ import with_statement

import sys

from greenhouse import compat, scheduler, util


__all__ = ["OneWayPool", "Pool", "OrderedPool", "map", "PoolClosed"]

_STOP = object()


class PoolClosed(RuntimeError):
    """Exception raised to wake any coroutines blocked on :meth:`get<Pool.get>`
    calls when a pool is :meth:`closed<Pool.close>`
    """


class OneWayPool(object):
    """a pool whose workers have input only

    :param func: the function the workers should run repeatedly
    :type func: function
    :param size: the number of workers to run
    :type size: int

    this class can be used as a context manager, in which case :meth:`start` is
    called at entry and :meth:`close` is called on exit from the context.
    """
    def __init__(self, func, size=10):
        self.func = func
        self.size = size
        self.inq = util.Queue()
        self._closing = False

    def start(self):
        "start the pool's workers"
        for i in xrange(self.size):
            scheduler.schedule(self._runner)
        self._closing = False

    def close(self):
        """shut down the pool's workers

        this method sets the :attr:`closing` attribute, and once all queued
        work has been completed it will set the :attr:`closed` attribute
        """
        self._closing = True
        for i in xrange(self.size):
            self.inq.put(_STOP)

    __del__ = close

    @property
    def closing(self):
        "whether :meth:`close` has been called"
        return self._closing

    @property
    def closed(self):
        "the pool has been closed and all :meth:`put` items have been handled"
        return self._closing and self.inq._jobs_done.is_set()

    def _runner(self):
        while 1:
            input = self.inq.get()
            if input is _STOP:
                break
            self._handle_one(input)
            self.inq.task_done()

    def _handle_one(self, input):
        self._run_func(*input)

    def _run_func(self, args, kwargs):
        try:
            return self.func(*args, **kwargs), True
        except Exception:
            klass, exc, tb = sys.exc_info()
            return (klass, exc, tb), False

    def put(self, *args, **kwargs):
        """place a new item into the pool to be handled by the workers

        all positional and keyword arguments will be passed in as the arguments
        to the function run by the pool's workers
        """
        self.inq.put((args, kwargs))

    def join(self):
        """wait for the pool's input queue to be cleaned out

        .. note::
            this method will block until it has no more pending tasks
        """
        self.inq.join()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, klass, value, tb):
        self.close()


class Pool(OneWayPool):
    """a pool from which the function's return values can be retrieved

    this class supports use as a context manager just as :class:`OneWayPool`
    does, and it also supports iteration, in which case :meth:`get` results
    are yielded until the pool has been closed and all results pulled.
    """
    def __init__(self, *args, **kwargs):
        super(Pool, self).__init__(*args, **kwargs)
        self.outq = util.Queue()

    def __iter__(self):
        while True:
            try:
                yield self.get()
            except PoolClosed:
                return

    def _handle_one(self, input):
        self.outq.put(self._run_func(*input))

    def get(self):
        """retrieve a result from the pool

        if nothing is already completed when this method is called, it will
        block until something comes back

        if the pool's function exited via exception, that will come back as
        a result here as well, but will be re-raised in :meth:`get`.

        .. note::
            if there is nothing in the pool's output queue when this method is
            called, it will block until something is ready

        :returns:
            a return value from one of the function's invocations if it exited
            normally

        :raises:
            :class:`PoolClosed` if the pool was closed before a result could be
            produced for thie call

        :raises: any exception that was raised inside the worker function
        """
        if self.closed:
            raise PoolClosed()

        result, succeeded = self.outq.get()
        if not succeeded:
            klass, exc, tb = result
            raise klass, exc, tb
        return result

    def close(self):
        """shut down the pool's workers

        this method sets the :attr:`closing` attribute, lines up the
        :attr:`closed` attribute to be set once any queued data has been
        processed, and raises a PoolClosed() exception in any coroutines still
        blocked on :meth:`get`.
        """
        super(Pool, self).close()
        for waiter, waketime in self.outq._waiters:
            scheduler.schedule_exception(PoolClosed(), waiter)

    @property
    def closed(self):
        """the pool has been closed, all :meth:`put` items have been retrieved
        with :meth`get`."""
        return super(Pool, self).closed and self.outq.empty()


class OrderedPool(Pool):
    """a pool in which the results are produced in order

    :class:`Pool` can produce results in a different order than that in which
    they were :meth:`put<Pool.put>` if one function invocation blocks for
    longer than another, but this class enforces that nothing will be produced
    by :meth:`get` until the next one in the order in which they were
    :meth:`put`.

    this class supports context manager usage and iteration just as its parent
    class does.
    """
    def __init__(self, func, size=10):
        super(OrderedPool, self).__init__(func, size)
        self._putcount = 0
        self._getcount = 0
        self._cache = {}

    def _handle_one(self, input):
        count, input = input
        self.outq.put((count, self._run_func(*input)))

    def put(self, *args, **kwargs):
        """place a new item into the pool to be handled by the workers

        all positional and keyword arguments will be passed in as the arguments
        to the function run by the pool's workers
        """
        self.inq.put((self._putcount, (args, kwargs)))
        self._putcount += 1

    def get(self):
        """retrieve a result from the pool

        if nothing is already completed when this method is called, it will
        block until something comes back

        if the pool's function exited via exception, that will come back as
        a result here as well, but will be re-raised in :meth:`get`.

        .. note::
            if there is nothing in the pool's output queue when this method is
            called, it will block until something is ready

        :returns:
            a return value from one of the function's invocations if it exited
            normally

        :raises:
            :class:`PoolClosed` if the pool was closed before a result could be
            produced for thie call

        :raises: any exception that was raised inside the worker function
        """
        if self.closed:
            raise PoolClosed()

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
    """a parallelized work-alike to the built-in ``map`` function

    this function works by creating an :class:`OrderedPool` and placing all
    the arguments in :meth:`put<OrderedPool.put>` calls, and yielding items
    produced by the pool's :meth:`get<OrderedPool.get>` method.

    :param func: the mapper function to use
    :type func: function
    :param items: the items to use as the mapper's arguments
    :type items: iterable
    :param pool_size:
        the number of workers for the pool -- this amounts to the concurrency
        with which the map is accomplished (default 10)
    :type pool_size: int

    :returns:
        a lazy iterator (like python3's map or python2's itertools.imap) over
        the results of the mapping
    """
    with OrderedPool(func, pool_size) as pool:
        for count, item in enumerate(items):
            pool.put(item)

        for i in xrange(count + 1):
            yield pool.get()
