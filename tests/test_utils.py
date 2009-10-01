import time
import unittest

import greenhouse
import greenhouse.poller

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

    def test_timeout_callback(self):
        ev = greenhouse.Event()
        l = [False]

        @ev._add_timeout_callback
        def c():
            l[0] = True

        ev.wait(TESTING_TIMEOUT)
        greenhouse.pause()
        assert l[0]

    def test_timeout_callback_goes_away(self):
        ev = greenhouse.Event()
        l = [False]

        @ev._add_timeout_callback
        def c():
            l[0] = True

        @greenhouse.schedule_in(TESTING_TIMEOUT)
        def f():
            ev.set()

        # this should be cleared before the timeout hits
        ev.wait(TESTING_TIMEOUT * 2)

        # and this should get us past when the timeout would hit
        time.sleep(TESTING_TIMEOUT)
        greenhouse.pause()

        assert not l[0]

    def test_timeout_with_exception(self):
        ev = greenhouse.Event()

        class CustomError(Exception): pass

        @ev._add_timeout_callback
        def c():
            raise CustomError()

        self.assertRaises(CustomError, ev.wait, TESTING_TIMEOUT)

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

        assert not l[0]

        time.sleep(TESTING_TIMEOUT)
        greenhouse.pause()
        assert l[0]

    def test_cancels(self):
        l = [False]

        def f():
            l[0] = True

        timer = greenhouse.Timer(TESTING_TIMEOUT, f)

        assert not l[0]

        timer.cancel()

        time.sleep(TESTING_TIMEOUT)
        greenhouse.pause()
        assert not l[0]

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
    def test_fifo_order(self):
        q = greenhouse.Queue()
        q.put(5)
        q.put(7)
        assert q.get() == 5
        assert q.get() == 7

    def test_blocks(self):
        q = greenhouse.Queue()
        l = [False]

        @greenhouse.schedule
        def f():
            l[0] = True
            q.put(None)

        q.get()
        assert l[0]

    def test_nonblocking_raises_empty(self):
        q = greenhouse.Queue()
        self.assertRaises(q.Empty, q.get_nowait)

    def test_nonblocking_raises_full(self):
        q = greenhouse.Queue(2)
        q.put(1)
        q.put(2)

        self.assertRaises(q.Full, q.put_nowait, 3)

    def test_put_sized_nonblocking(self):
        q = greenhouse.Queue(3)
        q.put(4)
        q.put(5)
        q.put(6)
        self.assertRaises(q.Full, q.put, 7, blocking=False)

    def test_put_sized_blocking(self):
        l = [False]
        q = greenhouse.Queue(3)
        q.put(4)
        q.put(5)
        q.put(6)

        @greenhouse.schedule
        def f():
            q.put(7)
            l[0] = True

        greenhouse.pause()
        assert not l[0]

        assert q.get() == 4

        greenhouse.pause()
        assert l[0]


    def test_timeout(self):
        q = greenhouse.Queue()
        self.assertRaises(q.Empty, q.get, timeout=TESTING_TIMEOUT)

    def test_joins(self):
        l = [False]
        q = greenhouse.Queue()
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
        q = greenhouse.Queue()
        q.put(1)

        q.task_done()
        self.assertRaises(ValueError, q.task_done)

    def test_empty_method(self):
        q = greenhouse.Queue()
        assert q.empty()

        q.put(5)
        assert not q.empty()

        q.get()
        assert q.empty()

    def test_full_method(self):
        q = greenhouse.Queue(2)
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
        q = greenhouse.Queue()
        assert q.qsize() == 0

        q.put(4)
        q.put(5)
        assert q.qsize() == 2

        q.get()
        assert q.qsize() == 1

        q.put(6)
        q.put(7)
        assert q.qsize() == 3

if __name__ == '__main__':
    unittest.main()
