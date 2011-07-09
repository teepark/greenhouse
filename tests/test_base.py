import contextlib
import errno
import gc
import os
import random
import socket
import sys
import traceback
import unittest
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

import greenhouse


port = lambda: 8000 + os.getpid() # because i want to run multiprocess nose

TESTING_TIMEOUT = 0.05

GTL = greenhouse.Lock()

class StateClearingTestCase(unittest.TestCase):
    def setUp(self):
        GTL.acquire()

        state = greenhouse.scheduler.state
        state.awoken_from_events.clear()
        state.timed_paused.clear()
        state.paused[:] = []
        state.descriptormap.clear()
        state.to_run.clear()
        del state.global_exception_handlers[:]
        state.local_exception_handlers.clear()
        del state.global_trace_hooks[:]
        state.local_to_trace_hooks.clear()
        state.local_from_trace_hooks.clear()

        greenhouse.poller.set()

    def tearDown(self):
        gc.collect()
        GTL.release()

    @contextlib.contextmanager
    def socketpair(self):
        server = greenhouse.Socket()
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        while 1:
            try:
                port = random.randrange(1025, 65536)
                server.bind(("", port))
            except socket.error, exc:
                if exc.args[0] != errno.EADDRINUSE:
                    raise
            else:
                break
        server.listen(5)

        client = greenhouse.Socket()
        client.connect(("", port))

        handler, addr = server.accept()
        server.close()

        yield client, handler

        client.close()
        handler.close()
