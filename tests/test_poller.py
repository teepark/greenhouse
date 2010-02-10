import select
import unittest

import greenhouse
import greenhouse.poller

from test_base import TESTING_TIMEOUT, StateClearingTestCase


class PollSelectorTestCase(StateClearingTestCase):
    def setUp(self):
        StateClearingTestCase.setUp(self)
        self._epoll = getattr(select, "epoll", None)
        self._poll = getattr(select, "poll", None)

    def tearDown(self):
        super(PollSelectorTestCase, self).tearDown()
        if self._epoll:
            select.epoll = self._epoll
        if self._poll:
            select.poll = self._poll

    def test_best(self):
        if hasattr(select, "epoll"):
            assert isinstance(greenhouse.poller.best(),
                    greenhouse.poller.Epoll)
            del select.epoll

        if hasattr(select, "poll"):
            assert isinstance(greenhouse.poller.best(), greenhouse.poller.Poll)
            del select.poll

        assert isinstance(greenhouse.poller.best(), greenhouse.poller.Select)


class PollerMixin(object):
    def setUp(self):
        StateClearingTestCase.setUp(self)
        greenhouse.poller.set(self.POLLER())

    def test_register_both_read_and_write(self):
        with self.socketpair() as (client, handler):
            poller = greenhouse._state.state.poller
            poller.register(client, poller.INMASK)

            poller.register(client, poller.OUTMASK)

    def test_skips_registering(self):
        sock = greenhouse.Socket()
        poller = greenhouse._state.state.poller

        poller.register(sock, poller.INMASK | poller.OUTMASK)

        items = poller._registry.items()

        poller.register(sock, poller.INMASK)

        self.assertEquals(poller._registry.items(), items)

    def test_poller_registration_rollback(self):
        with self.socketpair() as (client, handler):
            r = [False]

            @greenhouse.schedule
            def client_recv():
                assert client.recv(10) == "hiya"
                r[0] = True
            greenhouse.pause()

            client.sendall("howdy")
            assert handler.recv(10) == "howdy"

            greenhouse.pause()
            assert not r[0]

            handler.sendall("hiya")
            greenhouse.pause_for(TESTING_TIMEOUT)
            assert r[0]

if greenhouse.poller.Epoll._POLLER:
    class EpollerTestCase(PollerMixin, StateClearingTestCase):
        POLLER = greenhouse.poller.Epoll

if greenhouse.poller.Poll._POLLER:
    class PollerTestCase(PollerMixin, StateClearingTestCase):
        POLLER = greenhouse.poller.Poll

class SelectTestCase(PollerMixin, StateClearingTestCase):
    POLLER = greenhouse.poller.Select


if __name__ == '__main__':
    unittest.main()
