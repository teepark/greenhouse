from __future__ import with_statement

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

        self.assertEqual(len(pool.inq._data), 30)

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

    def test_exception_resiliency(self):
        l = []

        count = 5

        def runner(item):
            if item < count:
                raise AttributeError("blah")
            l.append(item ** 2)

        pool = self.POOL(runner, count)
        pool.start()

        for i in xrange(count):
            pool.put(i)

        greenhouse.pause()
        self.assertEqual(l, [])

        for i in xrange(count, count * 3):
            pool.put(i)

        greenhouse.pause()
        self.assertEqual(sorted(l), [x ** 2 for x in xrange(count, count * 3)])

        pool.close()


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

    def test_get_raises(self):
        count = 5

        def runner(item):
            if item < count:
                raise AttributeError("blah")
            else:
                return item ** 2

        pool = self.POOL(runner, count)
        pool.start()

        for i in xrange(count):
            pool.put(i)

        for i in xrange(count):
            self.assertRaises(AttributeError, pool.get)

        for i in xrange(count, count * 3):
            pool.put(i)

        l = []
        for i in xrange(count * 2):
            l.append(pool.get())

        self.assertEqual(sorted(l), [x ** 2 for x in xrange(count, count * 3)])

        pool.close()

    def test_getters_raise_on_close(self):
        l = []
        raised = [False]

        def runner(item):
            return item ** 2

        pool = self.POOL(runner, 5)
        pool.start()

        @greenhouse.schedule
        def getter():
            try:
                while 1:
                    l.append(pool.get())
            except StandardError:
                raised[0] = True

        for i in xrange(10):
            pool.put(i)
        greenhouse.pause()

        self.assertEqual(l, [x ** 2 for x in xrange(10)])

        pool.close()
        greenhouse.pause()

        assert raised[0]

    def test_iteration(self):
        def runner(x):
            if x > 10:
                pool.close()
            return x ** 2

        def putter(pool):
            i = 0
            while 1:
                i += 1
                pool.put(i)
                greenhouse.pause()

        pool = self.POOL(runner, 3)
        pool.start()

        greenhouse.schedule(putter, args=(pool,))

        results = []
        for item in pool:
            results.append(item)

        self.assertEqual(results, [x ** 2 for x in xrange(1, 11)])


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
