from __future__ import with_statement

import sys
import time
import unittest

import greenhouse
import greenhouse.poller
from greenhouse import util

from test_base import TESTING_TIMEOUT, StateClearingTestCase


class EventsTestCase(StateClearingTestCase):
    def test_isSet(self):
        ev = greenhouse.Event()
        assert not ev.is_set()
        ev.set()
        assert ev.is_set()

    def test_blocks(self):
        ev = greenhouse.Event()
        l = [False]

        @greenhouse.schedule
        def f():
            ev.wait()
            l[0] = True

        greenhouse.pause()
        greenhouse.pause()
        greenhouse.pause()

        assert not l[0]

    def test_nonblocking_when_set(self):
        ev = greenhouse.Event()
        l = [False]
        ev.set()

        @greenhouse.schedule
        def f():
            ev.wait()
            l[0] = True

        greenhouse.pause()

        assert l[0]

    def test_unblocks(self):
        ev = greenhouse.Event()
        l = [False]

        @greenhouse.schedule
        def f():
            ev.wait()
            l[0] = True

        greenhouse.pause()
        greenhouse.pause()
        greenhouse.pause()

        assert not l[0]

        ev.set()
        greenhouse.pause()

        assert l[0]

    def test_timeouts(self):
        ev = greenhouse.Event()
        start = time.time()
        ev.wait(TESTING_TIMEOUT)
        now = time.time()
        assert now - start > TESTING_TIMEOUT, now - start

    def test_timeouts_in_grlets(self):
        l = [False]
        ev = greenhouse.Event()

        @greenhouse.schedule
        def f():
            ev.wait(TESTING_TIMEOUT)
            l[0] = True

        greenhouse.pause()
        assert not l[0]

        greenhouse.pause_for(TESTING_TIMEOUT * 2)

        assert l[0]

    def test_timeout_clears_waiters(self):
        ev = greenhouse.Event()
        l = [False]

        @greenhouse.schedule
        def f():
            ev.wait(TESTING_TIMEOUT)
            l[0] = True

        greenhouse.pause_for(TESTING_TIMEOUT * 2)

        assert l[0]

        self.assertEqual(ev._waiters, [])

class LockTestCase(StateClearingTestCase):
    LOCK = greenhouse.Lock

    def test_locks(self):
        lock = self.LOCK()
        assert not lock.locked()
        lock.acquire()
        assert lock.locked()

    def test_blocks(self):
        lock = self.LOCK()
        l = [False]

        @greenhouse.schedule
        def f():
            lock.acquire()
            l[0] = True
            lock.release()

        lock.acquire()
        greenhouse.pause()
        greenhouse.pause()
        greenhouse.pause()

        assert not l[0]

    def test_returns_false_nonblocking(self):
        lock = self.LOCK()

        @greenhouse.schedule
        def f():
            assert not lock.acquire(blocking=False)

        lock.acquire()
        greenhouse.pause()

    def test_blocks_same_grlet(self):
        lock = self.LOCK()
        lock.acquire()
        assert not lock.acquire(blocking=False)
        lock.release()

    def test_fails_on_bad_release_attempt(self):
        lock = self.LOCK()
        self.assertRaises(RuntimeError, lock.release)

    def test_usage_as_context_manager(self):
        lock = self.LOCK()
        l = [0]

        @greenhouse.schedule
        def f():
            with lock:
                l[0] += 1

        with lock:
            l[0] += 1
            greenhouse.pause()
            assert l[0] == 1

        greenhouse.pause()
        assert l[0] == 2

    def test_release_race(self):
        lock = self.LOCK()
        l = []

        @greenhouse.schedule
        def f():
            lock.acquire()
            greenhouse.pause()
            lock.release()

        @greenhouse.schedule
        def g1():
            lock.acquire()
            l.append(1)

        @greenhouse.schedule
        def g2():
            lock.acquire()
            l.append(2)

        # let f grab the lock and the gs get blocked
        greenhouse.pause()

        # this time f releases, and it should only wake up one of the gs
        greenhouse.pause()
        greenhouse.pause()
        greenhouse.pause()

        self.assertEquals(len(l), 1)


class RLockTestCase(LockTestCase):
    LOCK = greenhouse.RLock

    def test_blocks_same_grlet(self):
        lock = self.LOCK()
        lock.acquire()
        assert lock.acquire(blocking=False)

    def test_isowned_method(self):
        lock = self.LOCK()
        assert not lock._is_owned()

        lock.acquire()
        assert lock._is_owned()

class ConditionRLockTestCase(StateClearingTestCase):
    LOCK = greenhouse.RLock

    def test_must_acquire_to_operate(self):
        cond = greenhouse.Condition(self.LOCK())
        self.assertRaises(RuntimeError, cond.notify)
        self.assertRaises(RuntimeError, cond.wait)
        self.assertRaises(RuntimeError, cond.notify_all)

    def test_owned_by_someone_else(self):
        cond = greenhouse.Condition(self.LOCK())

        @greenhouse.schedule
        def f():
            cond.acquire()
            greenhouse.pause()
        greenhouse.pause()

        self.assertRaises(RuntimeError, cond.notify)
        self.assertRaises(RuntimeError, cond.wait)
        self.assertRaises(RuntimeError, cond.notify_all)

        greenhouse.pause()

    def test_notify_wakes_up_one_at_a_time(self):
        cond = greenhouse.Condition(self.LOCK())
        l = []

        def schedule_new_appender(i):
            @greenhouse.schedule
            def f():
                cond.acquire()
                cond.wait()
                cond.release()

                l.append(i)

        map(schedule_new_appender, xrange(10))
        greenhouse.pause()

        assert len(l) == 0

        for i in xrange(10):
            cond.acquire()
            cond.notify()
            cond.release()

            greenhouse.pause()

            assert len(l) == i + 1, (len(l), i)

        greenhouse.pause()
        assert len(l) == 10

    def test_notify_all_wakes_everyone(self):
        cond = greenhouse.Condition(self.LOCK())
        l = []

        def schedule_new_appender(i):
            @greenhouse.schedule
            def f():
                cond.acquire()
                cond.wait()
                cond.release()

                l.append(i)

        map(schedule_new_appender, xrange(10))
        greenhouse.pause()

        cond.acquire()
        cond.notify_all()
        cond.release()

        greenhouse.pause()
        assert len(l) == 10

    def test_waiting_with_timeouts(self):
        cond = greenhouse.Condition(self.LOCK())
        l = []

        def schedule_new_appender(i):
            @greenhouse.schedule
            def f():
                cond.acquire()
                cond.wait(TESTING_TIMEOUT)
                cond.release()

                l.append(i)

        map(schedule_new_appender, xrange(10))
        greenhouse.pause()

        time.sleep(TESTING_TIMEOUT * 2)
        greenhouse.pause()

        assert len(l) == 10, l


class ConditionLockTestCase(ConditionRLockTestCase):
    LOCK = greenhouse.Lock

class CommonSemaphoreTests(object):
    def test_blocks(self):
        sem = self.SEM()
        sem.acquire()
        assert not sem.acquire(blocking=False)

    def test_releasing_awakens(self):
        sem = self.SEM()
        l = [False]

        @greenhouse.schedule
        def f():
            sem.acquire()
            l[0] = True

        sem.acquire()
        greenhouse.pause()
        greenhouse.pause()
        assert not l[0]

        sem.release()
        greenhouse.pause()
        assert l[0]

    def test_as_context_manager(self):
        sem = self.SEM()
        l = [False]

        @greenhouse.schedule
        def f():
            with sem:
                l[0] = True

        with sem:
            greenhouse.pause()
            greenhouse.pause()
            assert not l[0]

        greenhouse.pause()
        assert l[0]

class SemaphoreTestCase(CommonSemaphoreTests, StateClearingTestCase):
    SEM = greenhouse.Semaphore

    def test_counting(self):
        sem = self.SEM()

        for i in xrange(10):
            sem.release()

        for i in xrange(11):
            assert sem.acquire(blocking=False)

        assert not sem.acquire(blocking=False)

class BoundedSemaphoreTestCase(CommonSemaphoreTests, StateClearingTestCase):
    SEM = greenhouse.BoundedSemaphore

    def test_cant_release(self):
        sem = self.SEM()
        self.assertRaises(ValueError, sem.release)

class TimerTestCase(StateClearingTestCase):
    def test_pauses(self):
        l = [False]

        def f():
            l[0] = True

        timer = greenhouse.Timer(TESTING_TIMEOUT, f)
        timer.start()

        assert not l[0]

        greenhouse.pause_for(TESTING_TIMEOUT * 2)
        assert l[0]

    def test_cancels(self):
        l = [False]

        def f():
            l[0] = True

        timer = greenhouse.Timer(TESTING_TIMEOUT, f)
        timer.start()

        assert not l[0]

        timer.cancel()

        greenhouse.pause_for(TESTING_TIMEOUT * 2)
        assert not l[0]

    def test_args(self):
        l = [False]

        def f(x, y):
            l[0] = (x, y)

        timer = greenhouse.Timer(TESTING_TIMEOUT, f, args=(3, 76))
        timer.start()

        assert not l[0]

        greenhouse.pause_for(TESTING_TIMEOUT * 2)
        self.assertEqual(l[0], (3, 76))

    def test_kwargs(self):
        l = [False]

        def f(**kwargs):
            l[0] = kwargs

        timer = greenhouse.Timer(TESTING_TIMEOUT, f, kwargs={'a': 1, 'b': 2})
        timer.start()

        assert not l[0]

        greenhouse.pause_for(TESTING_TIMEOUT * 2)
        self.assertEqual(l[0], {'a': 1, 'b': 2})

class LocalTestCase(StateClearingTestCase):
    def test_different_values(self):
        #1
        loc = greenhouse.Local()
        loc.foo = "main"

        @greenhouse.schedule
        def f():
            # 2
            loc.foo = "f"
            greenhouse.pause() # to 3
            # 4
            assert loc.foo == "f"

        greenhouse.pause() # to 2
        # 3
        assert loc.foo == "main"
        greenhouse.pause() # to 4

    def test_attribute_error(self):
        #1
        loc = greenhouse.Local()

        @greenhouse.schedule
        def f():
            # 2
            loc.foo = "f"
            greenhouse.pause() # to 3

        greenhouse.pause() # to 2
        # 3
        self.assertRaises(AttributeError, lambda: loc.foo)

class QueueTestCase(StateClearingTestCase):
    klass = greenhouse.Queue

    def test_order(self):
        q = self.klass()
        l = [32, 17, 0, 34, 3, 18, 41, 21, 14, 29, 28, 35, 15, 47, 9, 8, 44,
                30, 20, 46, 25, 24, 36, 11, 12, 38, 10, 19, 23, 13, 31, 4, 7,
                39, 27, 1, 2, 40, 33, 6, 26, 22, 48, 5, 49, 45, 42, 16, 43, 37]
        map(q.put, l)

        for item in l:
            self.assertEqual(q.get(), item)

    def test_blocks(self):
        q = self.klass()
        l = [False]

        @greenhouse.schedule
        def f():
            q.put(None)
            l[0] = True

        q.get()
        assert l[0]

    def test_nonblocking_raises_empty(self):
        q = self.klass()
        self.assertRaises(util.Empty, q.get_nowait)
        self.assertRaises(util.Empty, q.get, block=False)

    def test_nonblocking_raises_full(self):
        q = self.klass(2)
        q.put(1)
        q.put(2)

        self.assertRaises(util.Full, q.put_nowait, 3)
        self.assertRaises(util.Full, q.put, 3, block=False)

    def test_put_sized_nonblocking(self):
        q = self.klass(3)
        q.put(4)
        q.put(5)
        q.put(6)
        self.assertRaises(util.Full, q.put, 7, block=False)

    def test_put_sized_blocking(self):
        l = [False]
        q = self.klass(3)
        q.put(4)
        q.put(5)
        q.put(6)

        @greenhouse.schedule
        def f():
            q.put(7)
            l[0] = True

        greenhouse.pause()
        assert not l[0]

        q.get()

        greenhouse.pause()
        assert l[0]

    def test_timeout(self):
        q = self.klass()
        self.assertRaises(util.Empty, q.get, timeout=TESTING_TIMEOUT)

    def test_joins(self):
        l = [False]
        q = self.klass()
        q.put(1)

        @greenhouse.schedule
        def f():
            q.join()
            l[0] = True

        greenhouse.pause()
        assert not l[0]

        q.get()
        greenhouse.pause()
        assert not l[0]

        q.task_done()
        greenhouse.pause()
        assert l[0]

    def test_calling_task_done_too_many_times(self):
        q = self.klass()
        q.put(1)

        q.task_done()
        self.assertRaises(ValueError, q.task_done)

    def test_empty_method(self):
        q = self.klass()
        assert q.empty()

        q.put(5)
        assert not q.empty()

        q.get()
        assert q.empty()

    def test_full_method(self):
        q = self.klass(2)
        assert not q.full()

        q.put(4)
        assert not q.full()

        q.put(5)
        assert q.full()

        q.get()
        assert not q.full()

        q.put(6)
        assert q.full()

    def test_qsize(self):
        q = self.klass()
        assert q.qsize() == 0

        q.put(4)
        q.put(5)
        assert q.qsize() == 2

        q.get()
        assert q.qsize() == 1

        q.put(6)
        q.put(7)
        assert q.qsize() == 3


class LifoQueueTestCase(QueueTestCase):
    klass = greenhouse.LifoQueue

    def test_order(self):
        q = self.klass()
        l = [32, 17, 0, 34, 3, 18, 41, 21, 14, 29, 28, 35, 15, 47, 9, 8, 44,
                30, 20, 46, 25, 24, 36, 11, 12, 38, 10, 19, 23, 13, 31, 4, 7,
                39, 27, 1, 2, 40, 33, 6, 26, 22, 48, 5, 49, 45, 42, 16, 43, 37]
        map(q.put, l)

        for item in l[::-1]:
            self.assertEqual(q.get(), item)


class PriorityQueueTestCase(QueueTestCase):
    klass = greenhouse.PriorityQueue

    def test_order(self):
        q = self.klass()
        l = [32, 17, 0, 34, 3, 18, 41, 21, 14, 29, 28, 35, 15, 47, 9, 8, 44,
                30, 20, 46, 25, 24, 36, 11, 12, 38, 10, 19, 23, 13, 31, 4, 7,
                39, 27, 1, 2, 40, 33, 6, 26, 22, 48, 5, 49, 45, 42, 16, 43, 37]
        map(q.put, l)

        for item in sorted(l):
            self.assertEqual(q.get(), item)


class ThreadTestCase(StateClearingTestCase):
    def test_order(self):
        l = []

        class T(greenhouse.util.Thread):
            def run(self):
                l.append(1)

        class T2(greenhouse.util.Thread):
            def run(self):
                l.append(2)

        t = T()
        t.start()

        t2 = T2()
        t2.start()

        greenhouse.pause()

        self.assertEqual(l, [1, 2])

    def test_args(self):
        s = set()

        class WithArgs(greenhouse.util.Thread):
            def run(self, num):
                s.add(num)

        threads = [WithArgs(args=(x,)) for x in xrange(5)]
        [t.start() for t in threads]

        greenhouse.pause()

        self.assertEqual(s, set(xrange(5)))

    def test_kwargs(self):
        d = {}

        class WithKwargs(greenhouse.util.Thread):
            def run(self, **kwargs):
                d.update(kwargs)

        threads = [WithKwargs(kwargs={chr(x): x}) for x in xrange(97, 123)]
        [t.start() for t in threads]

        greenhouse.pause()

        self.assertEqual(
                d,
                dict((chr(x), x) for x in xrange(97, 123)))

    def test_args_and_kwargs(self):
        s = set()

        class WithArgs(greenhouse.util.Thread):
            def run(self, num):
                s.add(num)

        a1 = WithArgs(args=(1,))
        a2 = WithArgs(args=(2,))
        a3 = WithArgs(args=(3,))

        a1.start()
        a2.start()
        a3.start()

        class WithKwargs(greenhouse.util.Thread):
            def run(self, **kwargs):
                s.update(kwargs.keys())

        k1 = WithKwargs(kwargs={'foo': 1})
        k2 = WithKwargs(kwargs={'bar': 1})

        k1.start()
        k2.start()

        self.assertEqual(s, set())

        greenhouse.pause()

        self.assertEqual(s, set([1, 2, 3, 'foo', 'bar']))

    def test_join(self):
        ev = greenhouse.util.Event()

        class T(greenhouse.util.Thread):
            def run(self):
                ev.wait()

        threads = [T() for i in xrange(5)]
        [t.start() for t in threads]

        l = []

        @greenhouse.schedule
        def joiner():
            threads[2].join()
            l.append(None)

        greenhouse.pause_for(TESTING_TIMEOUT)

        self.assertEqual(len(l), 0)

        ev.set()
        greenhouse.pause()
        greenhouse.pause()

        self.assertEqual(len(l), 1)


class CounterTestCase(StateClearingTestCase):
    def test_counts(self):
        c = util.Counter()

        self.assertEqual(c.count, 0)

        c.increment()
        c.increment()
        c.increment()

        self.assertEqual(c.count, 3)

        c.decrement()
        c.decrement()

        self.assertEqual(c.count, 1)

    def test_blocks(self):
        c = util.Counter()
        c.increment()

        l = [0]

        @greenhouse.schedule
        def f():
            c.wait()
            l[0] += 1

        greenhouse.pause()

        self.assertEqual(l[0], 0)

    def test_releases(self):
        c = util.Counter()
        c.increment()

        l = [0]

        @greenhouse.schedule
        def f():
            c.wait()
            l[0] += 1

        greenhouse.pause()

        self.assertEqual(l[0], 0)

        c.decrement()
        greenhouse.pause()

        self.assertEqual(l[0], 1)

    def test_releases_up(self):
        c = util.Counter()

        l = [0]

        @greenhouse.schedule
        def f():
            c.wait(4)
            l[0] += 1

        greenhouse.pause()

        for i in xrange(4):
            self.assertEqual(l[0], 0)
            c.increment()
            greenhouse.pause()

        self.assertEqual(l[0], 1)


if __name__ == '__main__':
    unittest.main()
