import array
import os
import socket
import stat
import tempfile
import threading
import time
import unittest

import greenhouse

from test_base import TESTING_TIMEOUT, StateClearingTestCase


PORT = 8123

class MonkeyPatchingTestCase(StateClearingTestCase):
    def test_monkeypatch(self):
        greenhouse.monkeypatch()

        assert open is greenhouse.File
        assert file is greenhouse.File
        assert socket.socket is greenhouse.Socket

    def test_unmonkeypatch(self):
        _sock = socket.socket
        _open = open
        _file = file

        greenhouse.monkeypatch()
        greenhouse.unmonkeypatch()

        assert socket.socket is _sock
        assert open is _open
        assert file is _file

class SocketTestCase(StateClearingTestCase):
    def makeserversock(self):
        sock = greenhouse.Socket()
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", PORT))
        sock.listen(5)

        return sock

    def test_sockets_basic(self):
        server = self.makeserversock()
        client = greenhouse.Socket()

        client.connect(("", PORT))
        handler, addr = server.accept()

        client.send("howdy")
        assert handler.recv(5) == "howdy"

        handler.send("hello, world")
        assert client.recv(12) == "hello, world"

        handler.close()
        client.close()
        server.close()

    def test_partial_recv(self):
        server = self.makeserversock()
        client = greenhouse.Socket()

        client.connect(("", PORT))
        handler, addr = server.accept()

        handler.send("this is a long message")

        assert client.recv(4) == "this"
        assert client.recv(3) == " is"
        assert client.recv(2) == " a"
        assert client.recv(5) == " long"
        assert client.recv(40) == " message"

    def test_recv_with_closed_sock(self):
        server = self.makeserversock()
        client = greenhouse.Socket()

        client.connect(("", PORT))
        handler, addr = server.accept()

        client.close()
        self.assertRaises(socket.error, client.recv, 10)

    def test_recvfrom(self):
        server = self.makeserversock()
        client = greenhouse.Socket()

        client.connect(("", PORT))
        handler, addr = server.accept()

        client.send("howdy")
        assert handler.recvfrom(5)[0] == "howdy"

        handler.send("hello, world")
        assert client.recvfrom(12)[0] == "hello, world"

        handler.close()
        client.close()
        server.close()

    def test_recv_into(self):
        server = self.makeserversock()
        client = greenhouse.Socket()

        client.connect(("", PORT))
        handler, addr = server.accept()

        collector = array.array('c', '\0' * 5)
        client.send("howdy")
        handler.recv_into(collector, 5)
        assert collector.tostring() == "howdy"

        collector = array.array('c', '\0' * 12)
        handler.send("hello, world")
        client.recv_into(collector, 12)
        assert collector.tostring() == "hello, world"

        handler.close()
        client.close()
        server.close()

    def test_recvfrom_into(self):
        server = self.makeserversock()
        client = greenhouse.Socket()

        client.connect(("", PORT))
        handler, addr = server.accept()

        collector = array.array('c', '\0' * 5)
        client.send("howdy")
        handler.recvfrom_into(collector, 5)
        assert collector.tostring() == "howdy"

        collector = array.array('c', '\0' * 12)
        handler.send("hello, world")
        client.recvfrom_into(collector, 12)
        assert collector.tostring() == "hello, world"

        handler.close()
        client.close()
        server.close()

    def test_sendall(self):
        server = self.makeserversock()
        client = greenhouse.Socket()

        client.connect(("", PORT))
        handler, addr = server.accept()

        client.sendall("howdy")
        assert handler.recv(5) == "howdy"

        handler.sendall("hello, world")
        assert client.recv(12) == "hello, world"

        handler.close()
        client.close()
        server.close()

    def test_sendto(self):
        server = self.makeserversock()
        client = greenhouse.Socket()

        client.connect(("", PORT))
        handler, addr = server.accept()

        client.sendto("howdy", ("", PORT))
        assert handler.recv(5) == "howdy"

        handler.close()
        client.close()
        server.close()

    def test_sockopts(self):
        sock = greenhouse.Socket()
        assert sock.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR) == 0
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        assert sock.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR) == 1

    # shutting down the reading end seems to have no effect on stdlib sockets,
    # so verify that it has no effect on greenhouse.Sockets either
    def test_shutdown_reading(self):
        server = self.makeserversock()
        client = greenhouse.Socket()

        client.connect(("", PORT))
        handler, addr = server.accept()

        client.shutdown(socket.SHUT_RD)

        handler.send("hello again")
        assert client.recv(11) == "hello again"

    def test_shutdown_writing(self):
        server = self.makeserversock()
        client = greenhouse.Socket()

        client.connect(("", PORT))
        handler, addr = server.accept()

        client.shutdown(socket.SHUT_WR)

        handler.send("hello")
        assert client.recv(5) == "hello"

        self.assertRaises(socket.error, client.send, "hello")

    def test_shutdown_rdwr(self):
        server = self.makeserversock()
        client = greenhouse.Socket()

        client.connect(("", PORT))
        handler, addr = server.accept()

        client.shutdown(socket.SHUT_RDWR)

        handler.send("hello")
        assert client.recv(5) == ""

        self.assertRaises(socket.error, client.send, "hello")

    def test_fromsock(self):
        server = self.makeserversock().dup()
        client = greenhouse.Socket().dup()

        client.connect(("", PORT))
        handler, addr = server.accept()
        handler = handler.dup()

        client.send("howdy")
        assert handler.recv(5) == "howdy"

        handler.send("hello, world")
        assert client.recv(12) == "hello, world"

        handler.close()
        client.close()
        server.close()

    def test_sockets_btwn_grlets(self):
        server = self.makeserversock()
        client = greenhouse.Socket()

        grlet_results = []

        @greenhouse.schedule
        def f():
            client.connect(("", PORT))
            client.send("hello from a greenlet")
            grlet_results.append(client.recv(19))

        handler, addr = server.accept()
        assert handler.recv(21) == "hello from a greenlet"

        handler.send("hello to a greenlet")
        greenhouse.pause()
        assert grlet_results[0] == "hello to a greenlet"

    def test_socketfile_read(self):
        server = self.makeserversock()
        client = greenhouse.Socket()

        client.connect(("", PORT))
        handler, addr = server.accept()

        reader = handler.makefile()
        results = []

        @greenhouse.schedule
        def f():
            results.append(reader.read())

        greenhouse.pause()
        assert not results

        client.send("this")
        greenhouse.pause()
        assert not results

        client.send(" is")
        greenhouse.pause()
        assert not results

        client.send(" a")
        greenhouse.pause()
        assert not results

        client.send(" test")
        greenhouse.pause()
        assert not results

        client.close()
        greenhouse.pause()
        assert results[0] == "this is a test"

    def test_socket_timeout(self):
        l = []
        server = self.makeserversock()
        client = greenhouse.Socket()

        client.connect(("", PORT))
        handler, addr = server.accept()

        client.settimeout(TESTING_TIMEOUT)

        @greenhouse.schedule
        def f():
            l.append(client.recv(10))

        greenhouse.pause()
        time.sleep(TESTING_TIMEOUT)
        greenhouse.pause()

        assert l and l[0] == ''

class FileTestCase(StateClearingTestCase):
    def setUp(self):
        self.fname = tempfile.mktemp()
        os.mknod(self.fname, 0644, stat.S_IFREG)

    def tearDown(self):
        os.unlink(self.fname)

    def test_basic_io(self):
        fp = greenhouse.File(self.fname, 'w')
        fp.write("this is testing text")
        fp.close()

        fp2 = greenhouse.File(self.fname, 'r')
        text = fp.read()
        fp2.close()

        assert text == "this is testing text"


if __name__ == '__main__':
    unittest.main()
