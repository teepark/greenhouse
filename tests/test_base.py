import sys
import unittest
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

import greenhouse


TESTING_TIMEOUT = 0.05

GTL = greenhouse.Lock()

class StateClearingTestCase(unittest.TestCase):
    def setUp(self):
        GTL.acquire()

        greenhouse.unmonkeypatch()

        state = greenhouse._state.state
        state.awoken_from_events.clear()
        state.timed_paused[:] = []
        state.paused[:] = []
        state.descriptormap.clear()
        state.to_run.clear()

        greenhouse.poller.set()

    def tearDown(self):
        GTL.release()
