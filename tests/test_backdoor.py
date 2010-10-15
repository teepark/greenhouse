import unittest

from greenhouse import backdoor, compat, io, scheduler

from test_base import TESTING_TIMEOUT, StateClearingTestCase, port


class BackdoorTests(StateClearingTestCase):
    def start_server(self, port, namespace=None):
        glet = scheduler.greenlet(
                backdoor.run_backdoor, args=(("127.0.0.1", port), namespace))
        scheduler.schedule(glet)
        scheduler.pause()

    def test_basic(self):
        self.start_server(8989)
        sock = io.Socket()
        sock.connect(("127.0.0.1", 8989))

        self.assertEqual(
                sock.recv(8192),
                '\n'.join((backdoor.PREAMBLE, backdoor.PS1)))

        sock.sendall("print 'hello'\n")

        self.assertEqual(sock.recv(6)[:6], 'hello\n')

        sock.close()

        scheduler.pause()
        scheduler.pause()


if __name__ == '__main__':
    unittest.main()
