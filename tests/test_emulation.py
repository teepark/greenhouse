import Queue
import socket
import thread
import threading
import unittest

from greenhouse import io, emulation, utils

from test_base import StateClearingTestCase


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


class BuiltinsTest(MonkeyPatchBase, StateClearingTestCase):
    PATCH_NAME = "builtins"

    PATCHES = [
        ('file', file, io.File, lambda: file),
        ('open', open, io.File, lambda: open),
    ]


class SocketTest(MonkeyPatchBase, StateClearingTestCase):
    PATCH_NAME = "socket"

    PATCHES = [
        ('socket', socket.socket, io.Socket, lambda: socket.socket),
        ('socketpair', socket.socketpair, emulation._green_socketpair,
            lambda: socket.socketpair),
        ('fromfd', socket.fromfd, io.sockets.socket_fromfd,
            lambda: socket.fromfd),
    ]


class ThreadTest(MonkeyPatchBase, StateClearingTestCase):
    PATCH_NAME = "thread"

    PATCHES = [
        ('allocate', thread.allocate, utils.Lock, lambda: thread.allocate),
        ('allocate_lock', thread.allocate_lock, utils.Lock,
            lambda: thread.allocate_lock),
        ('start_new', thread.start_new, emulation._green_start,
            lambda: thread.start_new),
        ('start_new_thread', thread.start_new_thread, emulation._green_start,
            lambda: thread.start_new_thread),
    ]


class ThreadingTest(MonkeyPatchBase, StateClearingTestCase):
    PATCH_NAME = "threading"

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
        ('current_thread', threading.current_thread, utils._current_thread,
            lambda: threading.current_thread),
        ('currentThread', threading.currentThread, utils._current_thread,
            lambda: threading.currentThread),
    ]


class QueueTest(MonkeyPatchBase, StateClearingTestCase):
    PATCH_NAME = "Queue"

    PATCHES = [
        ('Queue', Queue.Queue, utils.Queue, lambda: Queue.Queue),
    ]


if __name__ == '__main__':
    unittest.main()
