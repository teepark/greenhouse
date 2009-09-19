import time
import unittest

import greenhouse

from test_base import TESTING_TIMEOUT, StateClearingTestCase


class ScheduleTestCase(StateClearingTestCase):
    def test_schedule(self):
        l = []

        def f1():
            l.append(1)
        greenhouse.schedule(f1)

        @greenhouse.schedule
        def f2():
            l.append(2)

        @greenhouse.schedule(args=(3,))
        def f3(x):
            l.append(x)

        @greenhouse.schedule(kwargs={'x': 4})
        def f4(x=None):
            l.append(x)

        @greenhouse.compat.greenlet
        def f5():
            l.append(5)
        greenhouse.schedule(f5)

        greenhouse.pause()

        l.sort()
        assert l == [1, 2, 3, 4, 5]

    def test_schedule_at(self):
        at = time.time() + TESTING_TIMEOUT
        l = []

        def f1():
            l.append(1)
        greenhouse.schedule_at(at, f1)

        @greenhouse.schedule_at(at)
        def f2():
            l.append(2)

        @greenhouse.schedule_at(at, args=(3,))
        def f3(x):
            l.append(x)

        @greenhouse.schedule_at(at, kwargs={'x': 4})
        def f4(x=None):
            l.append(x)

        @greenhouse.compat.greenlet
        def f5():
            l.append(5)
        greenhouse.schedule_at(at, f5)

        greenhouse.pause()
        assert not l

        time.sleep(TESTING_TIMEOUT)
        greenhouse.pause()

        l.sort()
        assert l == [1, 2, 3, 4, 5]

    def test_schedule_in(self):
        l = []

        def f1():
            l.append(1)
        greenhouse.schedule_in(TESTING_TIMEOUT, f1)

        @greenhouse.schedule_in(TESTING_TIMEOUT)
        def f2():
            l.append(2)

        @greenhouse.schedule_in(TESTING_TIMEOUT, args=(3,))
        def f3(x):
            l.append(x)

        @greenhouse.schedule_in(TESTING_TIMEOUT, kwargs={'x': 4})
        def f4(x=None):
            l.append(x)

        @greenhouse.compat.greenlet
        def f5():
            l.append(5)
        greenhouse.schedule_in(TESTING_TIMEOUT, f5)

        greenhouse.pause()
        assert not l

        time.sleep(TESTING_TIMEOUT)
        greenhouse.pause()

        l.sort()
        assert l == [1, 2, 3, 4, 5]

    def test_schedule_recurring(self):
        l = []

        def f1():
            l.append(1)
        greenhouse.schedule_recurring(TESTING_TIMEOUT, f1, maxtimes=2)

        greenhouse.pause_for(TESTING_TIMEOUT * 3)
        assert l == [1, 1]

        l = []
        @greenhouse.schedule_recurring(TESTING_TIMEOUT, maxtimes=2)
        def f2():
            l.append(2)

        greenhouse.pause_for(TESTING_TIMEOUT * 3)
        assert l == [2, 2]

        l = []
        @greenhouse.schedule_recurring(TESTING_TIMEOUT, maxtimes=2, args=(3,))
        def f3(x):
            l.append(x)

        greenhouse.pause_for(TESTING_TIMEOUT * 3)
        assert l == [3, 3]

        l = []
        @greenhouse.schedule_recurring(TESTING_TIMEOUT, maxtimes=2,
                kwargs={'x': 4})
        def f4(x=None):
            l.append(x)

        greenhouse.pause_for(TESTING_TIMEOUT * 3)
        assert l == [4, 4]

        l = []
        @greenhouse.compat.greenlet
        def f5():
            l.append(5)
        greenhouse.schedule_recurring(TESTING_TIMEOUT, f5, maxtimes=2)

        greenhouse.pause_for(TESTING_TIMEOUT * 3)
        assert l == [5, 5], l

    def test_schedule_recurring_rejects_dead_grlet(self):
        @greenhouse.compat.greenlet
        def f():
            pass

        while not f.dead:
            f.switch()

        self.assertRaises(TypeError, greenhouse.schedule_recurring,
                TESTING_TIMEOUT, f, maxtimes=2)

class TimedPausingTestCase(StateClearingTestCase):
    def test_pause_for(self):
        start = time.time()
        greenhouse.pause_for(TESTING_TIMEOUT)
        assert TESTING_TIMEOUT + 0.01 > time.time() - start >= TESTING_TIMEOUT

    def test_pause_until(self):
        until = time.time() + TESTING_TIMEOUT
        greenhouse.pause_until(until)
        assert until + 0.01 > time.time() >= until


if __name__ == '__main__':
    unittest.main()
