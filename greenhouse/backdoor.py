from __future__ import with_statement

import code
import contextlib
import socket
import subprocess
import sys
import traceback
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from greenhouse import io, scheduler


__all__ = ["run", "backdoor_handler"]


#TODO: a `hostname` subprocess is not likely to be that portable
HOST = subprocess.Popen(
        ["hostname"], stdout=subprocess.PIPE).communicate()[0].rstrip()
PREAMBLE = "Python %s on %s\nHost: %s" % (sys.version, sys.platform, HOST)
PS1 = getattr(sys, "ps1", ">>> ")
PS2 = getattr(sys, "ps2", "... ")


def run(address):
    serversock = io.Socket()
    serversock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    serversock.bind(address)
    serversock.listen(socket.SOMAXCONN)

    while 1:
        clientsock, address = serversock.accept()
        scheduler.schedule(backdoor_handler, args=(clientsock,))


@contextlib.contextmanager
def _wrap_stdio(stdout, stderr):
    stdout.seek(0)
    stderr.seek(0)
    stdout.truncate()
    stderr.truncate()

    real_stdout = sys.stdout
    real_stderr = sys.stderr

    sys.stdout = stdout
    sys.stderr = stderr

    yield

    sys.stdout = real_stdout
    sys.stderr = real_stderr


def backdoor_handler(clientsock):
    @scheduler.schedule_in(10)
    def f():
        clientsock.shutdown(socket.SHUT_RDWR)

    console = code.InteractiveConsole()
    clientfile = clientsock.makefile('r')
    multiline_statement = []
    stdout, stderr = StringIO(), StringIO()

    clientsock.sendall(PREAMBLE + "\n" + PS1)

    for input_line in clientsock.makefile('r'):
        input_line = input_line.rstrip()

        with _wrap_stdio(stdout, stderr):
            source = '\n'.join(multiline_statement) + input_line
            result = console.runsource(source)

        clientsock.sendall(stdout.getvalue())
        err = stderr.getvalue()
        if err:
            clientsock.sendall(err)

        if result and not err:
            multiline_statement.append(input_line)
            clientsock.sendall(PS2)
            continue

        multiline_statement = []
        clientsock.sendall(PS1)
