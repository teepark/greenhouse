import os
import socket
import time
import unittest

import greenhouse
import greenhouse.poller

from test_base import TESTING_TIMEOUT, StateClearingTestCase


port = lambda: 8000 + os.getpid() # because i'm running multiprocess nose

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
        dmap = greenhouse._state.state.descriptormap
        fno = greenhouse.Socket().fileno()

        import gc
        gc.collect()

        assert all(x() is None for x in dmap[fno]), [x() for x in dmap(fno)]

        client = greenhouse.Socket()
        server = greenhouse.Socket()
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("", port()))
        server.listen(5)
        client.connect(("", port()))
        handler, addr = server.accept()

        handler.send("howdy")
        client.recv(5)

        assert all(x() for x in dmap[fno]), [x() for x in dmap[fno]]

        handler.close()
        client.close()
        server.close()

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

class PausingTestCase(StateClearingTestCase):
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

class ExceptionsTestCase(StateClearingTestCase):
    class CustomError(Exception): pass

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


if __name__ == '__main__':
    unittest.main()
