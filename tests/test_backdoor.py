import unittest

from greenhouse import backdoor, compat, io, scheduler

from test_base import TESTING_TIMEOUT, StateClearingTestCase, port


class BackdoorTests(StateClearingTestCase):
    def start_server(self, port, namespace=None):
        scheduler.schedule(
                backdoor.run_backdoor, args=(("127.0.0.1", port), namespace))
        scheduler.pause()

    def test_basic(self):
        self.start_server(8989)
        sock = io.Socket()
        sock.connect(("127.0.0.1", 8989))

        self.assertEqual(
                sock.recv(8192),
                '\n'.join((backdoor.PREAMBLE, backdoor.PS1)))

        sock.sendall("print 'hello'\n")

        self.assertEqual(sock.recv(8192), 'hello\n' + backdoor.PS1)

        sock.close()

    def test_nonshared_namespaces(self):
        namespace = {}
        self.start_server(8991, namespace)

        sock1 = io.Socket()
        sock1.connect(("127.0.0.1", 8991))
        self.assertEqual(
                sock1.recv(8192),
                '\n'.join((backdoor.PREAMBLE, backdoor.PS1)))

        sock2 = io.Socket()
        sock2.connect(("127.0.0.1", 8991))
        self.assertEqual(
                sock2.recv(8192),
                '\n'.join((backdoor.PREAMBLE, backdoor.PS1)))

        sock1.sendall("seven = 7\n")
        self.assertEqual(sock1.recv(8192), backdoor.PS1)

        sock2.sendall("'seven' in locals()\n")
        self.assertEqual(sock2.recv(8192), "False\n" + backdoor.PS1)

        sock2.sendall("seven = 4\n")
        self.assertEqual(sock2.recv(8192), backdoor.PS1)

        sock1.sendall("seven\n")
        self.assertEqual(sock1.recv(8192), "7\n" + backdoor.PS1)


if __name__ == '__main__':
    unittest.main()
