from __future__ import with_statement

import Queue
import select
import socket
import sys
import thread
import threading
import unittest

from greenhouse import io, emulation, poller, scheduler, util

from test_base import StateClearingTestCase, TESTING_TIMEOUT


class MonkeyPatchBase(object):
    PATCH_NAME = ""

    def tearDown(self):
        super(MonkeyPatchBase, self).tearDown()
        emulation.unpatch()

    def test_enable(self):
        emulation.patch(self.PATCH_NAME)

        for name, standard, patched, getter in self.PATCHES:
            val = getter()
            assert val is patched, (name, val)

    def test_disable(self):
        emulation.unpatch(self.PATCH_NAME)

        for name, standard, patched, getter in self.PATCHES:
            val = getter()
            assert val is standard, (name, val)


#class PatchBuiltinsTest(MonkeyPatchBase, StateClearingTestCase):
#    PATCH_NAME = "__builtin__"
#
#    PATCHES = [
#        ('file', file, io.File, lambda: file),
#        ('open', open, io.File, lambda: open),
#    ]


class PatchSocketTest(MonkeyPatchBase, StateClearingTestCase):
    PATCH_NAME = "socket"

    PATCHES = [
        ('socket', socket.socket, io.Socket, lambda: socket.socket),
        ('socketpair', socket.socketpair, emulation.socket.green_socketpair,
            lambda: socket.socketpair),
        ('fromfd', socket.fromfd, io.sockets.socket_fromfd,
            lambda: socket.fromfd),
    ]


class PatchThreadTest(MonkeyPatchBase, StateClearingTestCase):
    PATCH_NAME = "thread"

    PATCHES = [
        ('allocate', thread.allocate, util.Lock, lambda: thread.allocate),
        ('allocate_lock', thread.allocate_lock, util.Lock,
            lambda: thread.allocate_lock),
        ('start_new', thread.start_new, emulation.threading.green_start,
            lambda: thread.start_new),
        ('start_new_thread', thread.start_new_thread,
            emulation.threading.green_start, lambda: thread.start_new_thread),
    ]


class PatchThreadingTest(MonkeyPatchBase, StateClearingTestCase):
    PATCH_NAME = "threading"

    PATCHES = [
        ('Event', threading.Event, util.Event, lambda: threading.Event),
        ('Lock', threading.Lock, util.Lock, lambda: threading.Lock),
        ('RLock', threading.RLock, util.RLock, lambda: threading.RLock),
        ('Condition', threading.Condition, util.Condition,
            lambda: threading.Condition),
        ('Semaphore', threading.Semaphore, util.Semaphore,
            lambda: threading.Semaphore),
        ('BoundedSemaphore', threading.BoundedSemaphore,
            util.BoundedSemaphore, lambda: threading.BoundedSemaphore),
        ('Timer', threading.Timer, util.Timer, lambda: threading.Timer),
        ('Thread', threading.Thread, util.Thread, lambda: threading.Thread),
        ('local', threading.local, util.Local, lambda: threading.local),
        ('currentThread', threading.currentThread, util._current_thread,
            lambda: threading.currentThread),
    ]

    if hasattr(threading, "current_thread"):
        PATCHES.append(('current_thread', threading.current_thread, util._current_thread,
            lambda: threading.current_thread))


class PatchQueueTest(MonkeyPatchBase, StateClearingTestCase):
    PATCH_NAME = "Queue"

    PATCHES = [
        ('Queue', Queue.Queue, util.Queue, lambda: Queue.Queue),
    ]


class PatchSysTest(MonkeyPatchBase, StateClearingTestCase):
    PATCH_NAME = "sys"

    PATCHES = [
        ('stdin', sys.stdin, io.files.stdin, lambda: sys.stdin),
        ('stdout', sys.stdout, io.files.stdout, lambda: sys.stdout),
        ('stderr', sys.stderr, io.files.stderr, lambda: sys.stderr),
    ]


class PatchedModules(StateClearingTestCase):
    def test_httplib(self):
        import socket as socket1, httplib as httplib1
        assert httplib1.socket.socket is socket1.socket

        green = emulation.patched("httplib")
        assert green.socket.socket is io.Socket
        assert green.socket.socketpair is emulation.socket.green_socketpair
        assert green.socket.fromfd is io.sockets.socket_fromfd

        import socket, httplib
        assert socket is socket1
        assert socket.socket is socket1.socket
        assert httplib is httplib1
        assert httplib1.socket.socket is httplib.socket.socket

    def test_urllib(self):
        import socket as socket1, urllib as urllib1
        assert urllib1.socket.socket is socket1.socket

        green = emulation.patched("urllib")
        assert green.socket.socket is io.Socket
        assert green.socket.socketpair is emulation.socket.green_socketpair
        assert green.socket.fromfd is io.sockets.socket_fromfd

        import socket, urllib
        assert socket is socket1
        assert socket.socket is socket1.socket
        assert urllib is urllib1
        assert urllib.socket.socket is urllib1.socket.socket

    def test_logging(self):
        import thread as thread1, threading as threading1, logging as logging1
        assert logging1.thread is thread1
        assert logging1.threading is threading1

        green = emulation.patched("logging")
        assert green.thread.allocate_lock is util.Lock
        assert green.thread.allocate is util.Lock
        assert green.thread.start_new_thread is emulation.threading.green_start
        assert green.thread.start_new is emulation.threading.green_start
        assert green.threading.Event is util.Event
        assert green.threading.Lock is util.Lock
        assert green.threading.RLock is util.RLock
        assert green.threading.Condition is util.Condition
        assert green.threading.Semaphore is util.Semaphore
        assert green.threading.BoundedSemaphore is util.BoundedSemaphore
        assert green.threading.Timer is util.Timer
        assert green.threading.Thread is util.Thread
        assert green.threading.local is util.Local
        assert green.threading.enumerate is util._enumerate_threads
        assert green.threading.active_count is util._active_thread_count
        assert green.threading.activeCount is util._active_thread_count
        assert green.threading.current_thread is util._current_thread
        assert green.threading.currentThread is util._current_thread

        import thread, threading, logging
        assert logging.thread.allocate_lock is thread1.allocate_lock
        assert logging.thread.allocate is thread1.allocate
        assert logging.thread.start_new_thread is thread1.start_new_thread
        assert logging.thread.start_new is thread1.start_new
        assert logging.threading.Event is threading1.Event
        assert logging.threading.Lock is threading1.Lock
        assert logging.threading.RLock is threading1.RLock
        assert logging.threading.Condition is threading1.Condition
        assert logging.threading.Semaphore is threading1.Semaphore
        assert logging.threading.BoundedSemaphore is threading1.BoundedSemaphore
        assert logging.threading.Timer is threading1.Timer
        assert logging.threading.Thread is threading1.Thread
        assert logging.threading.local is threading1.local
        assert logging.threading.enumerate is threading1.enumerate
        assert logging.threading.active_count is threading1.active_count
        assert logging.threading.activeCount is threading1.activeCount
        assert logging.threading.current_thread is threading1.current_thread
        assert logging.threading.currentThread is threading1.currentThread
        assert logging.thread.allocate_lock is thread.allocate_lock
        assert logging.thread.allocate is thread.allocate
        assert logging.thread.start_new_thread is thread.start_new_thread
        assert logging.thread.start_new is thread.start_new
        assert logging.threading.Event is threading.Event
        assert logging.threading.Lock is threading.Lock
        assert logging.threading.RLock is threading.RLock
        assert logging.threading.Condition is threading.Condition
        assert logging.threading.Semaphore is threading.Semaphore
        assert logging.threading.BoundedSemaphore is threading.BoundedSemaphore
        assert logging.threading.Timer is threading.Timer
        assert logging.threading.Thread is threading.Thread
        assert logging.threading.local is threading.local
        assert logging.threading.enumerate is threading.enumerate
        assert logging.threading.active_count is threading.active_count
        assert logging.threading.activeCount is threading.activeCount
        assert logging.threading.current_thread is threading.current_thread
        assert logging.threading.currentThread is threading.currentThread

    def test_socketserver(self):
        green = emulation.patched("asyncore")
        assert green.select.select is emulation.select.green_select
        assert getattr(green.select, "poll", emulation.select.green_poll) is \
                emulation.select.green_poll
        assert getattr(green.select, "epoll",
                emulation.select.green_epoll) is emulation.select.green_epoll
        assert getattr(green.select, "kqueue", emulation.select.green_kqueue) \
                is emulation.select.green_kqueue


class GreenSelectMixin(object):
    def setUp(self):
        super(GreenSelectMixin, self).setUp()
        scheduler.reset_poller(self.POLLER())

    def test_select(self):
        with self.socketpair() as (client, server):
            rlist, wlist, xlist = emulation.select.green_select(
                    [client, server], [client, server], [], 0)
            assert client not in rlist
            assert client in wlist
            assert server not in rlist
            assert server in wlist

            client.send("hello")

            rlist, wlist, xlist = emulation.select.green_select(
                    [client, server], [client, server], [], 0)
            assert client not in rlist
            assert client in wlist
            assert server in rlist
            assert server in wlist

    if hasattr(select, "poll"):
        def test_poll(self):
            with self.socketpair() as (client, server):
                p = emulation.select.green_poll()
                p.register(client, select.POLLIN | select.POLLOUT)
                p.register(server, select.POLLIN | select.POLLOUT)
                events = dict(p.poll(0))
                assert events[client.fileno()] & select.POLLOUT
                assert not events[client.fileno()] & select.POLLIN
                assert events[server.fileno()] & select.POLLOUT
                assert not events[server.fileno()] & select.POLLIN

                client.send("hello")

                events = dict(p.poll(TESTING_TIMEOUT))
                assert events[client.fileno()] & select.POLLOUT
                assert not events[client.fileno()] & select.POLLIN
                assert events[server.fileno()] & select.POLLOUT
                assert events[server.fileno()] & select.POLLIN

    if hasattr(select, "epoll"):
        def test_epoll(self):
            with self.socketpair() as (client, server):
                ep = emulation.select.green_epoll()
                ep.register(client, select.EPOLLIN | select.EPOLLOUT)
                ep.register(server, select.EPOLLIN | select.EPOLLOUT)
                events = dict(ep.poll(0))
                assert events[client.fileno()] & select.EPOLLOUT
                assert not events[client.fileno()] & select.EPOLLIN
                assert events[server.fileno()] & select.EPOLLOUT
                assert not events[server.fileno()] & select.EPOLLIN

                client.send("hello")

                events = dict(ep.poll(TESTING_TIMEOUT))
                assert events[client.fileno()] & select.EPOLLOUT
                assert not events[client.fileno()] & select.EPOLLIN
                assert events[server.fileno()] & select.EPOLLOUT
                assert events[server.fileno()] & select.EPOLLIN

    if hasattr(select, "kqueue"):
        def test_kqueue(self):
            with self.socketpair() as (client, server):
                kq = emulation.select.green_kqueue()
                events = [
                        select.kevent(client.fileno(), select.KQ_FILTER_READ,
                            select.KQ_EV_ADD),
                        select.kevent(client.fileno(), select.KQ_FILTER_WRITE,
                            select.KQ_EV_ADD),
                        select.kevent(server.fileno(), select.KQ_FILTER_READ,
                            select.KQ_EV_ADD),
                        select.kevent(server.fileno(), select.KQ_FILTER_WRITE,
                            select.KQ_EV_ADD)]

                if sys.platform == 'darwin':
                    for event in events:
                        # stupid busted OS X kqueue
                        kq.control([event], 0)
                else:
                    kq.control(events, 0)

                events = [(ke.ident, ke.filter)
                        for ke in kq.control(None, 4, 0)]
                assert (client.fileno(), select.KQ_FILTER_WRITE) in events
                assert (client.fileno(), select.KQ_FILTER_READ) not in events
                assert (server.fileno(), select.KQ_FILTER_WRITE) in events
                assert (server.fileno(), select.KQ_FILTER_READ) not in events

                client.send("hello")

                events = [(ke.ident, ke.filter)
                        for ke in kq.control(None, 4, 0)]
                assert (client.fileno(), select.KQ_FILTER_WRITE) in events
                assert (client.fileno(), select.KQ_FILTER_READ) not in events
                assert (server.fileno(), select.KQ_FILTER_WRITE) in events
                assert (server.fileno(), select.KQ_FILTER_READ) in events


class GreenSelectWithSelectPollerTests(
        GreenSelectMixin, StateClearingTestCase):
    POLLER = poller.Select

if hasattr(select, "poll"):
    class GreenSelectWithPollPollerTests(
            GreenSelectMixin, StateClearingTestCase):
        POLLER = poller.Poll

if hasattr(select, "epoll"):
    class GreenSelectWithEpollPollerTests(
            GreenSelectMixin, StateClearingTestCase):
        POLLER = poller.Epoll

if hasattr(select, "kqueue"):
    class GreenSelectWithKQueuePollerTests(
            GreenSelectMixin, StateClearingTestCase):
        POLLER = poller.KQueue


if __name__ == '__main__':
    unittest.main()
