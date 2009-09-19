import os
import socket
import stat
import tempfile
import threading
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
        greenhouse.unmonkeypatch()

        _sock = socket.socket
        _open = open
        _file = file

        greenhouse.monkeypatch()
        greenhouse.unmonkeypatch()

        assert socket.socket is _sock
        assert open is _open
        assert file is _file

class SocketTestCase(StateClearingTestCase):
    def test_sockets_basic(self):
        server = greenhouse.Socket()
        client = greenhouse.Socket()

        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("", PORT))
        server.listen(5)

        client.connect(("", PORT))
        handler, addr = server.accept()

        client.send("howdy")
        assert handler.recv(5) == "howdy"

        handler.send("hello, world")
        assert client.recv(12) == "hello, world"

        handler.close()
        client.close()
        server.close()

    def test_sockets_btwn_grlets(self):
        server = greenhouse.Socket()
        client = greenhouse.Socket()

        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("", PORT))
        server.listen(5)

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
