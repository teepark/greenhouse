import Queue
import socket
import thread
import threading
import unittest

from greenhouse import io, monkeypatch, utils

from test_base import StateClearingTestCase


class MonkeyPatchBase(object):
    def tearDown(self):
        super(MonkeyPatchBase, self).tearDown()
        self.disable_patch()

    def test_enable(self):
        self.enable_patch()

        for name, standard, patched, getter in self.PATCHES:
            val = getter()
            assert val is patched, (name, val)

    def test_disable(self):
        self.enable_patch()
        self.disable_patch()

        for name, standard, patched, getter in self.PATCHES:
            val = getter()
            assert val is standard, (name, val)


class BuiltinsTest(MonkeyPatchBase, StateClearingTestCase):
    PATCHES = [
        ('file', file, io.File, lambda: file),
        ('open', open, io.File, lambda: open),
    ]

    def enable_patch(self):
        monkeypatch.builtins()

    def disable_patch(self):
        monkeypatch.builtins(False)


class SocketTest(MonkeyPatchBase, StateClearingTestCase):
    PATCHES = [
        ('socket', socket.socket, io.Socket, lambda: socket.socket),
        ('socketpair', socket.socketpair, monkeypatch._green_socketpair,
            lambda: socket.socketpair),
        ('fromfd', socket.fromfd, io.socket_fromfd, lambda: socket.fromfd),
    ]

    def enable_patch(self):
        monkeypatch.socket()

    def disable_patch(self):
        monkeypatch.socket(False)


class ThreadTest(MonkeyPatchBase, StateClearingTestCase):
    PATCHES = [
        ('allocate', thread.allocate, utils.Lock, lambda: thread.allocate),
        ('allocate_lock', thread.allocate_lock, utils.Lock,
            lambda: thread.allocate_lock),
        ('start_new', thread.start_new, monkeypatch._green_start,
            lambda: thread.start_new),
        ('start_new_thread', thread.start_new_thread, monkeypatch._green_start,
            lambda: thread.start_new_thread),
    ]

    def enable_patch(self):
        monkeypatch.thread()

    def disable_patch(self):
        monkeypatch.thread(False)


class ThreadingTest(MonkeyPatchBase, StateClearingTestCase):
    PATCHES = [
        ('Event', threading.Event, utils.Event, lambda: threading.Event),
        ('Lock', threading.Lock, utils.Lock, lambda: threading.Lock),
        ('RLock', threading.RLock, utils.RLock, lambda: threading.RLock),
        ('Condition', threading.Condition, utils.Condition,
            lambda: threading.Condition),
        ('Semaphore', threading.Semaphore, utils.Semaphore,
            lambda: threading.Semaphore),
        ('BoundedSemaphore', threading.BoundedSemaphore,
            utils.BoundedSemaphore, lambda: threading.BoundedSemaphore),
        ('Timer', threading.Timer, utils.Timer, lambda: threading.Timer),
        ('Thread', threading.Thread, utils.Thread, lambda: threading.Thread),
        ('local', threading.local, utils.Local, lambda: threading.local),
    ]

    def enable_patch(self):
        monkeypatch.threading()

    def disable_patch(self):
        monkeypatch.threading(False)


class QueueTest(MonkeyPatchBase, StateClearingTestCase):
    PATCHES = [
        ('Queue', Queue.Queue, utils.Queue, lambda: Queue.Queue),
    ]

    def enable_patch(self):
        monkeypatch.queue()

    def disable_patch(self):
        monkeypatch.queue(False)


if __name__ == '__main__':
    unittest.main()
