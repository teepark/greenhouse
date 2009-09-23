import unittest

import greenhouse
import greenhouse.poller

from test_base import TESTING_TIMEOUT, StateClearingTestCase


class PoolTestCase(StateClearingTestCase):
    POOL = greenhouse.Pool

    def test_basic(self):
        def f(x):
            return x ** 2

        pool = self.POOL(f)
        pool.start()

        for x in xrange(30):
            pool.put(x)

        l = []
        for x in xrange(30):
            l.append(pool.get())

        l.sort()
        assert l == [x ** 2 for x in xrange(30)]

        pool.close()

    def test_with_blocking(self):
        def f(x):
            if x % 2:
                greenhouse.pause()
            return x ** 2

        pool = self.POOL(f)
        pool.start()

        for x in xrange(30):
            pool.put(x)

        l = []
        for x in xrange(30):
            l.append(pool.get())

        l.sort()
        assert l == [x ** 2 for x in xrange(30)]

        pool.close()

    def test_shuts_down(self):
        def f(x):
            return x ** 2

        pool = self.POOL(f)
        pool.start()

        for x in xrange(30):
            pool.put(x)

        for x in xrange(30):
            pool.get()

        pool.close()

        for x in xrange(30):
            pool.put(x)

        greenhouse.pause()

        assert len(pool.inq.queue) == 30, len(pool.inq.queue)

    def test_as_context_manager(self):
        def f(x):
            return x ** 2

        with self.POOL(f) as pool:
            for x in xrange(30):
                pool.put(x)

            l = []
            for x in xrange(30):
                l.append(pool.get())

            l.sort()
            assert l == [x ** 2 for x in xrange(30)]

    def test_starting_back_up(self):
        def f(x):
            return x ** 2

        pool = self.POOL(f)
        pool.start()

        for x in xrange(30):
            pool.put(x)

        for x in xrange(30):
            pool.get()

        pool.close()

        greenhouse.pause()

        pool.start()

        for x in xrange(30):
            pool.put(x)

        l = []
        for x in xrange(30):
            l.append(pool.get())

        l.sort()
        assert l == [x ** 2 for x in xrange(30)]

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
