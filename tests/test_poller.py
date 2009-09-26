import select
import unittest

import greenhouse
import greenhouse.poller

from test_base import TESTING_TIMEOUT, StateClearingTestCase


class PollSelectorTestCase(StateClearingTestCase):
    def setUp(self):
        StateClearingTestCase.setUp(self)
        self._epoll = select.epoll
        self._poll = select.poll
        self._select = select.select

    def tearDown(self):
        super(PollSelectorTestCase, self).tearDown()
        select.epoll = self._epoll
        select.poll = self._poll
        select.select = self._select

    def test_best(self):
        assert isinstance(greenhouse.poller.best(), greenhouse.poller.Epoll)

        del select.epoll
        assert isinstance(greenhouse.poller.best(), greenhouse.poller.Poll)

        del select.poll
        assert isinstance(greenhouse.poller.best(), greenhouse.poller.Select)


class PollRegistryTestCase(StateClearingTestCase):
    POLLER = greenhouse.poller.Poll

    def setUp(self):
        StateClearingTestCase.setUp(self)
        greenhouse.poller.set(self.POLLER())

    def test_skips_registering(self):
        sock = greenhouse.Socket()
        poller = greenhouse._state.state.poller

        poller.register(sock, poller.INMASK | poller.OUTMASK)

        items = poller._registry.items()

        poller.register(sock, poller.INMASK)

        self.assertEquals(poller._registry.items(), items)

class EpollRegistryTestCase(PollRegistryTestCase):
    POLLER = greenhouse.poller.Epoll

class SelectRegistryTestCase(PollRegistryTestCase):
    POLLER = greenhouse.poller.Select


if __name__ == '__main__':
    unittest.main()
