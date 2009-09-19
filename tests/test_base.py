import sys
import unittest
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

import greenhouse


TESTING_TIMEOUT = 0.05

class StateClearingTestCase(unittest.TestCase):
    def setUp(self):
        greenhouse.unmonkeypatch()
        state = greenhouse._state.state
        state.paused_on_events.clear()
        state.awoken_from_events.clear()
        state.timed_paused[:] = []
        state.paused[:] = []
        state.descriptormap.clear()
        state.to_run.clear()
