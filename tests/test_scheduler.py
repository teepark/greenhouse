import os
import socket
import time
import unittest

import greenhouse
import greenhouse.poller

from test_base import TESTING_TIMEOUT, StateClearingTestCase


port = lambda: 8000 + os.getpid() # because i'm running multiprocess nose

class ScheduleMixin(object):
    def setUp(self):
        super(ScheduleMixin, self).setUp()
        greenhouse.poller.set(self.POLLER())

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

        greenhouse.pause_for(TESTING_TIMEOUT)

        l.sort()
        assert l == [1, 2, 3, 4, 5], l

    def test_schedule_at(self):
        at = time.time() + (TESTING_TIMEOUT * 2)
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

        greenhouse.pause_for(TESTING_TIMEOUT * 2)
        assert time.time() >= at
        greenhouse.pause()

        l.sort()
        assert l == [1, 2, 3, 4, 5], l

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
        assert l == [1, 2, 3, 4, 5], l

    def test_schedule_recurring(self):
        l = []

        def f1():
            l.append(1)
        greenhouse.schedule_recurring(TESTING_TIMEOUT, f1, maxtimes=2)

        greenhouse.pause_for(TESTING_TIMEOUT * 3)
        assert l == [1, 1], l

        l = []
        @greenhouse.schedule_recurring(TESTING_TIMEOUT, maxtimes=2)
        def f2():
            l.append(2)

        greenhouse.pause_for(TESTING_TIMEOUT * 3)
        assert l == [2, 2], l

        l = []
        @greenhouse.schedule_recurring(TESTING_TIMEOUT, maxtimes=2, args=(3,))
        def f3(x):
            l.append(x)

        greenhouse.pause_for(TESTING_TIMEOUT * 3)
        assert l == [3, 3], l

        l = []
        @greenhouse.schedule_recurring(TESTING_TIMEOUT, maxtimes=2,
                kwargs={'x': 4})
        def f4(x=None):
            l.append(x)

        greenhouse.pause_for(TESTING_TIMEOUT * 3)
        assert l == [4, 4], l

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

    def test_deleted_sock_gets_cleared(self):
        dmap = greenhouse.scheduler.state.descriptormap

        client = greenhouse.Socket()
        server = greenhouse.Socket()
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        temp = greenhouse.Socket()
        temps_fileno = temp.fileno()

        one_good = filter(lambda (r, w): r and w, dmap[temps_fileno])
        self.assertEqual(len(one_good), 1, one_good)

        del temp
        del one_good

        @greenhouse.schedule
        def f():
            server.bind(("", port()))
            server.listen(5)
            conn = server.accept()[0]
            assert conn.recv(8192) == "test_deleted_sock_gets_cleared"

        greenhouse.pause_for(TESTING_TIMEOUT)
        client.connect(("", port()))
        client.sendall("test_deleted_sock_gets_cleared")

        greenhouse.pause_for(TESTING_TIMEOUT)

        gone = filter(lambda (r, w): r and w, dmap[temps_fileno])
        self.assertEqual(len(gone), 0, gone)

    def test_socketpolling(self):
        client = greenhouse.Socket()
        server = greenhouse.Socket()
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("", port()))
        server.listen(5)
        client.connect(("", port()))
        handler, addr = server.accept()
        l = [False]

        @greenhouse.schedule
        def f():
            client.recv(10)
            l[0] = True

        greenhouse.pause()
        greenhouse.pause()
        assert not l[0]

        handler.send("hi")
        greenhouse.pause()
        assert l[0]

    def test_order(self):
        l = []

        @greenhouse.schedule
        def f():
            l.append(1)

        @greenhouse.schedule
        def f():
            l.append(2)

        greenhouse.pause()

        self.assertEqual(l, [1, 2])

    class CustomError(Exception): pass

    def test_pause(self):
        l = [False]

        @greenhouse.schedule
        def f():
            l[0] = True

        assert not l[0]

        greenhouse.pause()
        assert l[0]

    def test_pause_for(self):
        start = time.time()
        greenhouse.pause_for(TESTING_TIMEOUT)
        assert TESTING_TIMEOUT + 0.03 > time.time() - start >= TESTING_TIMEOUT

    def test_pause_until(self):
        until = time.time() + TESTING_TIMEOUT
        greenhouse.pause_until(until)
        assert until + 0.03 > time.time() >= until

    def test_exceptions_raised_in_grlets(self):
        l = [False]

        @greenhouse.schedule
        def f():
            raise self.CustomError()
            l[0] = True

        greenhouse.pause()
        greenhouse.pause()
        greenhouse.pause()
        greenhouse.pause()

        assert not l[0]

    def test_schedule_exception(self):
        l = [False]
        exc = []

        @greenhouse.schedule
        @greenhouse.greenlet
        def glet():
            try:
                greenhouse.pause()
            except Exception, err:
                exc.append(err)
                return
            l[0] = True

        greenhouse.pause()
        greenhouse.schedule_exception(self.CustomError(), glet)

        greenhouse.pause()

        assert not l[0]
        assert isinstance(exc[0], self.CustomError), exc

    def test_schedule_exception_rejects_funcs(self):
        def f(): pass
        self.assertRaises(
                TypeError, greenhouse.schedule_exception, Exception(), f)

    def test_schedule_exception_rejects_dead_glets(self):
        @greenhouse.schedule
        @greenhouse.greenlet
        def g():
            pass

        greenhouse.pause()
        self.assertRaises(
                ValueError, greenhouse.schedule_exception, Exception(), g)

    def test_schedule_exception_in(self):
        l = [False]
        excs = []

        @greenhouse.schedule
        @greenhouse.greenlet
        def glet():
            try:
                greenhouse.pause_for(TESTING_TIMEOUT * 2)
            except Exception, exc:
                excs.append(exc)
                return
            l[0] = True

        greenhouse.pause()
        greenhouse.schedule_exception_in(
                TESTING_TIMEOUT, self.CustomError(), glet)

        greenhouse.pause_for(TESTING_TIMEOUT * 2)

        assert not l[0]
        assert isinstance(excs[0], self.CustomError), excs

    def test_schedule_exception_in_rejects_funcs(self):
        def f(): pass
        self.assertRaises(
                TypeError, greenhouse.schedule_exception_in, 1, Exception(), f)

    def test_schedule_exception_in_rejects_dead_glets(self):
        @greenhouse.schedule
        @greenhouse.greenlet
        def g():
            pass

        greenhouse.pause()
        self.assertRaises(
                ValueError, greenhouse.schedule_exception_in, 1, Exception(), g)

    def test_schedule_exception_at(self):
        l = [False]
        excs = []

        @greenhouse.schedule
        @greenhouse.greenlet
        def glet():
            try:
                greenhouse.pause_until(time.time() + TESTING_TIMEOUT * 2)
            except Exception, exc:
                excs.append(exc)
                return
            l[0] = True

        greenhouse.pause()
        greenhouse.schedule_exception_at(
                time.time() + TESTING_TIMEOUT, self.CustomError(), glet)

        greenhouse.pause_until(time.time() + TESTING_TIMEOUT * 2)

        assert not l[0]
        assert isinstance(excs[0], self.CustomError), excs

    def test_schedule_exception_at_rejects_funcs(self):
        def f(): pass
        self.assertRaises(
                TypeError, greenhouse.schedule_exception_at,
                time.time() + 1, Exception(), f)

    def test_schedule_exception_at_rejects_dead_glets(self):
        @greenhouse.schedule
        @greenhouse.greenlet
        def g():
            pass

        greenhouse.pause()
        self.assertRaises(
                ValueError, greenhouse.schedule_exception_at,
                time.time() + 1, Exception(), g)

    def test_end(self):
        l = [False]

        @greenhouse.schedule
        @greenhouse.greenlet
        def glet():
            greenhouse.pause()
            l[0] = True

        greenhouse.pause()
        greenhouse.end(glet)

        greenhouse.pause()

        assert not l[0]

    def test_end_rejects_funcs(self):
        def f(): pass
        self.assertRaises(TypeError, greenhouse.end, f)

    def test_end_permits_dead_glets(self):
        @greenhouse.schedule
        @greenhouse.greenlet
        def g():
            pass

        greenhouse.pause()

        # no assert, just make sure we don't raise
        greenhouse.end(g)

    def test_global_exception_handlers(self):
        class CustomError(Exception):
            pass

        @greenhouse.schedule
        def f():
            raise CustomError()

        l = []

        def handler(klass, exc, tb):
            l.append(klass)

        greenhouse.add_global_exception_handler(handler)

        greenhouse.pause()

        self.assertEqual(len(l), 1)
        self.assertEqual(l[0], CustomError)

    def test_local_exception_handlers(self):
        class CustomError1(Exception):
            pass

        class CustomError2(Exception):
            pass

        l = []

        def handler(klass, exc, tb):
            l.append(klass)

        @greenhouse.schedule
        @greenhouse.greenlet
        def g1():
            raise CustomError1()

        @greenhouse.schedule
        @greenhouse.greenlet
        def g2():
            raise CustomError2()

        greenhouse.add_local_exception_handler(handler, g2)

        greenhouse.pause()

        self.assertEqual(len(l), 1)
        self.assertEqual(l[0], CustomError2)


class ScheduleTestsWithSelect(ScheduleMixin, StateClearingTestCase):
    POLLER = greenhouse.poller.Select

if greenhouse.poller.Poll._POLLER:
    class ScheduleTestsWithPoll(ScheduleMixin, StateClearingTestCase):
        POLLER = greenhouse.poller.Poll

if greenhouse.poller.Epoll._POLLER:
    class ScheduleTestsWithEpoll(ScheduleMixin, StateClearingTestCase):
        POLLER = greenhouse.poller.Epoll

if greenhouse.poller.KQueue._POLLER:
    class ScheduleTestsWithKQueue(ScheduleMixin, StateClearingTestCase):
        POLLER = greenhouse.poller.KQueue


try:
    import btree
except ImportError:
    pass
else:
    class BisectingScheduleTest(StateClearingTestCase):
        def setUp(self):
            super(BisectingScheduleTest, self).setUp()
            self._old_mgr = greenhouse.scheduler.state.timed_paused
            greenhouse.scheduler.BisectingTimeoutManager.install()

        def tearDown(self):
            type(self._old_mgr).install()
            super(BisectingScheduleTest, self).tearDown()

    BTreeScheduleTestsWithSelect = ScheduleTestsWithSelect
    BTreeScheduleTestsWithSelect.__name__ = "BTreeScheduleTestsWithSelect"
    del ScheduleTestsWithSelect

    class BisectingScheduleTestsWithSelect(ScheduleMixin, BisectingScheduleTest):
        POLLER = greenhouse.poller.Select

    if greenhouse.poller.Poll._POLLER:
        BTreeScheduleTestsWithPoll = ScheduleTestsWithPoll
        BTreeScheduleTestsWithPoll.__name__ = "BTreeScheduleTestsWithPoll"
        del ScheduleTestsWithPoll

        class BisectingScheduleTestsWithPoll(ScheduleMixin, BisectingScheduleTest):
            POLLER = greenhouse.poller.Poll

    if greenhouse.poller.Epoll._POLLER:
        BTreeScheduleTestsWithEpoll = ScheduleTestsWithEpoll
        BTreeScheduleTestsWithEpoll.__name__ = "BTreeScheduleTestsWithEpoll"
        del ScheduleTestsWithEpoll

        class BisectingScheduleTestsWithEpoll(
                ScheduleMixin, BisectingScheduleTest):
            POLLER = greenhouse.poller.Epoll

    if greenhouse.poller.KQueue._POLLER:
        BTreeScheduleTestsWithKQueue = ScheduleTestsWithKQueue
        BTreeScheduleTestsWithKQueue.__name__ = "BTreeScheduleTestsWithKQueue"
        del ScheduleTestsWithKQueue

        class BisectingScheduleTestsWithKQueue(
                ScheduleMixin, BisectingScheduleTest):
            POLLER = greenhouse.poller.KQueue


if __name__ == '__main__':
    unittest.main()
