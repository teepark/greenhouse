import select
import unittest

import greenhouse
import greenhouse.poller

from test_base import TESTING_TIMEOUT, StateClearingTestCase


class PollSelectorTestCase(StateClearingTestCase):
    def setUp(self):
        self._epoll = select.epoll
        self._poll = select.poll
        self._select = select.select

    def tearDown(self):
        select.epoll = self._epoll
        select.poll = self._poll
        select.select = self._select

    def test_best(self):
        assert isinstance(greenhouse.poller.best(), greenhouse.poller.Epoll)

        del select.epoll
        assert isinstance(greenhouse.poller.best(), greenhouse.poller.Poll)

        del select.poll
        assert isinstance(greenhouse.poller.best(), greenhouse.poller.Select)


if __name__ == '__main__':
    unittest.main()
