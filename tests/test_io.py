import array
import multiprocessing
import os
import socket
import stat
import tempfile
import threading
import time
import unittest

import greenhouse
import greenhouse.poller

from test_base import TESTING_TIMEOUT, StateClearingTestCase, port


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

class SocketPollerMixin(object):
    def test_sockets_basic(self):
        with self.socketpair() as (client, handler):
            client.send("howdy")
            assert handler.recv(5) == "howdy"

            handler.send("hello, world")
            assert client.recv(12) == "hello, world"

    def test_partial_recv(self):
        with self.socketpair() as (client, handler):
            handler.send("this is a long message")

            assert client.recv(4) == "this"
            assert client.recv(3) == " is"
            assert client.recv(2) == " a"
            assert client.recv(5) == " long"
            assert client.recv(40) == " message"

    def test_recv_with_closed_sock(self):
        with self.socketpair() as (client, handler):
            client.close()
            client._sock.close()
            self.assertRaises(socket.error, client.recv, 10)

    def test_recvfrom(self):
        with self.socketpair() as (client, handler):
            client.send("howdy")
            assert handler.recvfrom(5)[0] == "howdy"

            handler.send("hello, world")
            assert client.recvfrom(12)[0] == "hello, world"

    def test_recv_into(self):
        with self.socketpair() as (client, handler):
            collector = array.array('c', '\0' * 5)
            client.send("howdy")
            handler.recv_into(collector, 5)
            assert collector.tostring() == "howdy"

            collector = array.array('c', '\0' * 12)
            handler.send("hello, world")
            client.recv_into(collector, 12)
            assert collector.tostring() == "hello, world"

    def test_recvfrom_into(self):
        with self.socketpair() as (client, handler):
            collector = array.array('c', '\0' * 5)
            client.send("howdy")
            handler.recvfrom_into(collector, 5)
            assert collector.tostring() == "howdy"

            collector = array.array('c', '\0' * 12)
            handler.send("hello, world")
            client.recvfrom_into(collector, 12)
            assert collector.tostring() == "hello, world"

    def test_sendall(self):
        with self.socketpair() as (client, handler):
            client.sendall("howdy")
            assert handler.recv(5) == "howdy"

            handler.sendall("hello, world")
            assert client.recv(12) == "hello, world"

    def test_sendto(self):
        with self.socketpair() as (client, handler):
            client.sendto("howdy", ("", port()))
            assert handler.recv(5) == "howdy"

    def test_sockopts(self):
        sock = greenhouse.Socket()
        assert not sock.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        assert sock.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR)

    def test_shutdown_writing(self):
        with self.socketpair() as (client, handler):
            client.shutdown(socket.SHUT_WR)

            handler.send("hello")
            assert client.recv(5) == "hello"

            self.assertRaises(socket.error, client.send, "hello")

    def test_shutdown_rdwr(self):
        with self.socketpair() as (client, handler):
            client.shutdown(socket.SHUT_RDWR)

            handler.send("hello")
            assert client.recv(5) == ""

            self.assertRaises(socket.error, client.send, "hello")

    def test_sock_dups(self):
        with self.socketpair() as (client, handler):
            client = client.dup()
            handler = handler.dup()

            client.send("howdy")
            assert handler.recv(5) == "howdy"

            handler.send("hello, world")
            assert client.recv(12) == "hello, world"

    def test_sockets_btwn_grlets(self):
        with self.socketpair() as (client, handler):
            grlet_results = []

            @greenhouse.schedule
            def f():
                client.send("hello from a greenlet")
                grlet_results.append(client.recv(19))

            assert handler.recv(21) == "hello from a greenlet"

            handler.send("hello to a greenlet")
            greenhouse.pause()
            assert grlet_results[0] == "hello to a greenlet"

    def test_socketfile_read(self):
        with self.socketpair() as (client, handler):
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
            client._sock.close()
            greenhouse.pause()
            assert results[0] == "this is a test"

    def test_socket_timeout(self):
        with self.socketpair() as (client, handler):
            client.settimeout(TESTING_TIMEOUT)
            assert client.gettimeout() == TESTING_TIMEOUT

            self.assertRaises(socket.timeout, client.recv, 10)

    def test_socket_timeout_in_grlet(self):
        with self.socketpair() as (client, handler):
            client.settimeout(TESTING_TIMEOUT)
            assert client.gettimeout() == TESTING_TIMEOUT

            @greenhouse.schedule
            def f():
                self.assertRaises(socket.timeout, client.recv, 10)
                client.recv(10)

            greenhouse.pause()

    def test_fromfd_from_gsock(self):
        with self.socketpair() as (client, handler):
            client = greenhouse.Socket(fromsock=client)
            handler.send("hi")
            assert client.recv(2) == "hi"
            client.send("howdy")
            assert handler.recv(3) == "how"

    def test_block_on_accept(self):
        server = greenhouse.Socket()
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("", port()))
        server.listen(5)

        @greenhouse.schedule
        def f():
            client = greenhouse.Socket()
            client.connect(("", port()))
            client.send("howdy")

        handler, addr = server.accept()
        assert handler.recv(5) == "howdy"

    def test_getnames(self):
        with self.socketpair() as (client, handler):
            assert client.getsockname() == handler.getpeername()
            assert client.getpeername() == handler.getsockname()

if greenhouse.poller.Epoll._POLLER:
    class EpollSocketTestCase(SocketPollerMixin, StateClearingTestCase):
        def setUp(self):
            StateClearingTestCase.setUp(self)
            greenhouse.poller.set(greenhouse.poller.Epoll())

if greenhouse.poller.Poll._POLLER:
    class PollSocketTestCase(SocketPollerMixin, StateClearingTestCase):
        def setUp(self):
            StateClearingTestCase.setUp(self)
            greenhouse.poller.set(greenhouse.poller.Poll())

class SelectSocketTestCase(SocketPollerMixin, StateClearingTestCase):
    def setUp(self):
        StateClearingTestCase.setUp(self)
        greenhouse.poller.set(greenhouse.poller.Select())

class FilePollerMixin(object):
    def tearDown(self):
        super(FilePollerMixin, self).tearDown()
        if os.path.exists(self.fname):
            os.unlink(self.fname)

    def touch(self, path):
        greenhouse.mkfile(path)

    def test_basic_io(self):
        fp = greenhouse.File(self.fname, 'w')
        fp.write("this is testing text")
        fp.close()

        fp2 = greenhouse.File(self.fname, 'r')
        text = fp.read()
        fp2.close()

        assert text == "this is testing text"

    def test_fails_to_read_missing_file(self):
        self.assertRaises(IOError, greenhouse.File, self.fname, 'r')

    def test_fromfd(self):
        self.touch(self.fname)

        with open(self.fname, 'w') as stdfp:
            stdfp.write("sajgoiafjsoma;l al al;")

        with open(self.fname) as stdfp:
            gfp = greenhouse.File.fromfd(stdfp.fileno())
            assert gfp.read() == "sajgoiafjsoma;l al al;"

    def test_readline(self):
        self.touch(self.fname)

        with open(self.fname, 'w') as stdfp:
            stdfp.write("""this
is
a

test
""")

        gfp = greenhouse.File(self.fname)

        try:
            assert gfp.readline() == "this\n"
            assert gfp.readline() == "is\n"
            assert gfp.readline() == "a\n"
            assert gfp.readline() == "\n"
            assert gfp.readline() == "test\n"
        finally:
            gfp.close()

    def test_as_context_manager(self):
        with open(self.fname, 'w') as stdfp:
            stdfp.write("foo bar spam eggs")

        with greenhouse.File(self.fname) as gfp:
            assert gfp.read() == "foo bar spam eggs"

    def test_seek_and_tell(self):
        with open(self.fname, 'w') as fp:
            fp.write("foo bar spam eggs")

        fp = greenhouse.File(self.fname)
        try:
            assert fp.tell() == 0

            fp.seek(4)
            assert fp.tell() == 4
            assert fp.read(3) == "bar"

            fp.seek(-4, os.SEEK_END)
            assert fp.tell() == 13
            assert fp.read(4) == "eggs"
        finally:
            fp.close()

    def test_append_mode(self):
        with open(self.fname, 'w') as fp:
            fp.write("standard file\n")

        fp = greenhouse.File(self.fname, 'a')
        try:
            fp.write("greenhouse")
        finally:
            fp.close()

        with open(self.fname) as fp:
            assert fp.read() == "standard file\ngreenhouse"

    def test_readwrite_mode(self):
        fp = greenhouse.File(self.fname, 'r+')
        try:
            fp.write("this is a test")
            fp.seek(0)
            assert fp.read() == "this is a test"
        finally:
            fp.close()

    def test_iteration(self):
        with open(self.fname, 'w') as fp:
            fp.write("""this
is
a

test""")

        fp = greenhouse.File(self.fname)
        try:
            l = list(fp)
            assert l == ["this\n", "is\n", "a\n", "\n", "test"], l
        finally:
            fp.close()

    def test_readlines(self):
        with open(self.fname, 'w') as fp:
            fp.write("""this
is
a

test""")

        fp = greenhouse.File(self.fname)
        try:
            l = fp.readlines()
            assert l == ["this\n", "is\n", "a\n", "\n", "test"], l
        finally:
            fp.close()

    def test_incremental_reads(self):
        with open(self.fname, 'w') as fp:
            fp.write("this is a test")

        fp = greenhouse.File(self.fname)
        try:
            assert fp.read(4) == "this"
            assert fp.read(3) == " is"
            assert fp.read(2) == " a"
            assert fp.read(5) == " test"
            assert fp.read(1) == ""
        finally:
            fp.close()

    def test_writelines(self):
        lines = ["this\n", "is\n", "a\n", "test\n"]
        fp = greenhouse.File(self.fname, 'w')
        try:
            fp.writelines(lines)
        finally:
            fp.close()

        with open(self.fname) as fp:
            assert fp.read() == "".join(lines)

if greenhouse.poller.Epoll._POLLER:
    class FileWithEpollTestCase(FilePollerMixin, StateClearingTestCase):
        def setUp(self):
            StateClearingTestCase.setUp(self)
            self.fname = tempfile.mktemp()
            greenhouse.poller.set(greenhouse.poller.Epoll())

if greenhouse.poller.Poll._POLLER:
    class FileWithPollTestCase(FilePollerMixin, StateClearingTestCase):
        def setUp(self):
            StateClearingTestCase.setUp(self)
            self.fname = tempfile.mktemp()
            greenhouse.poller.set(greenhouse.poller.Poll())

class FileWithSelectTestCase(FilePollerMixin, StateClearingTestCase):
    def setUp(self):
        StateClearingTestCase.setUp(self)
        self.fname = tempfile.mktemp()
        greenhouse.poller.set(greenhouse.poller.Select())

class PipePollerMixin(object):
    def test_basic(self):
        rfp, wfp = greenhouse.pipe()
        try:
            wfp.write("howdy")
            assert rfp.read(5) == "howdy"
        finally:
            rfp.close()
            wfp.close()

    def test_blocking(self):
        rfp, wfp = greenhouse.pipe()
        l = []
        try:
            @greenhouse.schedule
            def f():
                l.append(rfp.read(4))

            greenhouse.pause()
            assert not l

            wfp.write("heyo")
            time.sleep(TESTING_TIMEOUT)
            greenhouse.pause()
            assert l and l[0] == "heyo"

        finally:
            rfp.close()
            wfp.close()

if greenhouse.poller.Epoll._POLLER:
    class PipeWithEpollTestCase(PipePollerMixin, StateClearingTestCase):
        def setUp(self):
            StateClearingTestCase.setUp(self)
            greenhouse.poller.set(greenhouse.poller.Epoll())

if greenhouse.poller.Poll._POLLER:
    class PipeWithPollTestCase(PipePollerMixin, StateClearingTestCase):
        def setUp(self):
            StateClearingTestCase.setUp(self)
            greenhouse.poller.set(greenhouse.poller.Poll())

class PipeWithSelectTestCase(PipePollerMixin, StateClearingTestCase):
    def setUp(self):
        StateClearingTestCase.setUp(self)
        greenhouse.poller.set(greenhouse.poller.Select())


if __name__ == '__main__':
    unittest.main()
