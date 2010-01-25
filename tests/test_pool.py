import unittest

import greenhouse
import greenhouse.poller

from test_base import TESTING_TIMEOUT, StateClearingTestCase


class OneWayPoolTestCase(StateClearingTestCase):
    POOL = greenhouse.OneWayPool

    def empty_out(self, pool, size):
        return []

    def test_shuts_down(self):
        def f(x):
            return x ** 2

        pool = self.POOL(f)
        pool.start()

        for x in xrange(30):
            pool.put(x)

        self.empty_out(pool, 30)

        pool.close()

        for x in xrange(30):
            pool.put(x)

        greenhouse.pause()

        assert len(pool.inq.queue) == 30, len(pool.inq.queue)

    def test_kills_all_coros(self):
        class Pool(self.POOL):
            def __init__(self, *args, **kwargs):
                super(Pool, self).__init__(*args, **kwargs)
                self.finished = []

            def _runner(self):
                super(Pool, self)._runner()
                self.finished.append(None)

        def f(x):
            return x ** 2

        pool = Pool(f)
        pool.start()

        for x in xrange(30):
            pool.put(x)

        self.empty_out(pool, 30)

        pool.close()

        greenhouse.pause()

        self.assertEqual(len(pool.finished), pool.size)

    def test_as_context_manager(self):
        l = []

        def f(x):
            l.append(x ** 2)

        with self.POOL(f) as pool:
            for x in xrange(30):
                pool.put(x)

        greenhouse.pause()
        greenhouse.pause()
        greenhouse.pause()

        l.sort()
        assert l == [x ** 2 for x in xrange(30)]


class PoolTestCase(OneWayPoolTestCase):
    POOL = greenhouse.Pool

    def empty_out(self, pool, size):
        return [pool.get() for i in xrange(size)]

    def test_as_context_manager(self):
        def f(x):
            return x ** 2

        with self.POOL(f) as pool:
            for x in xrange(30):
                pool.put(x)

            l = self.empty_out(pool, 30)

        l.sort()
        assert l == [x ** 2 for x in xrange(30)]

    def test_basic_two_way(self):
        def f(x):
            return x ** 2

        pool = self.POOL(f)
        pool.start()

        for x in xrange(30):
            pool.put(x)

        l = self.empty_out(pool, 30)

        l.sort()
        assert l == [x ** 2 for x in xrange(30)]

        pool.close()

    def test_starting_back_up(self):
        def f(x):
            return x ** 2

        pool = self.POOL(f)
        pool.start()

        for x in xrange(30):
            pool.put(x)

        self.empty_out(pool, 30)

        pool.close()

        greenhouse.pause()

        pool.start()

        for x in xrange(30):
            pool.put(x)

        l = self.empty_out(pool, 30)

        l.sort()
        assert l == [x ** 2 for x in xrange(30)]

    def test_two_way_with_blocking(self):
        def f(x):
            if x % 2:
                greenhouse.pause()
            return x ** 2

        pool = self.POOL(f)
        pool.start()

        for x in xrange(30):
            pool.put(x)

        l = self.empty_out(pool, 30)

        l.sort()
        assert l == [x ** 2 for x in xrange(30)]

        pool.close()


class OrderedPoolTestCase(PoolTestCase):
    POOL = greenhouse.OrderedPool

    def test_ordered_basic(self):
        def f(x):
            return x ** 2

        pool = self.POOL(f)
        pool.start()

        for x in xrange(30):
            pool.put(x)

        l = []
        for x in xrange(30):
            l.append(pool.get())

        assert l == [x ** 2 for x in xrange(30)]

        pool.close()

    def test_ordered_with_blocking(self):
        def f(x):
            if x % 2:
                greenhouse.pause()
                greenhouse.pause()
                greenhouse.pause()
            return x ** 2

        pool = self.POOL(f)
        pool.start()

        for x in xrange(30):
            pool.put(x)

        l = []
        for x in xrange(30):
            l.append(pool.get())

        assert l == [x ** 2 for x in xrange(30)]

        pool.close()


if __name__ == '__main__':
    unittest.main()
