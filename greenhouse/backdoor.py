from __future__ import with_statement

import code
import contextlib
import socket
import sys
import traceback
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from greenhouse import io, scheduler


__all__ = ["run_backdoor", "backdoor_handler"]


PREAMBLE = "Python %s on %s" % (sys.version, sys.platform)
PS1 = getattr(sys, "ps1", ">>> ")
PS2 = getattr(sys, "ps2", "... ")


def run_backdoor(address, locals_=None):
    '''start a server in the current coroutine that accepts connections on
    the specified address and starts backdoor interpreters on them

    locals_ is optionally a dictionary that will serve as the execution context
    for the connected interpreters. an empty dictionary would not put anything
    into the namespace, but would cause all connected backdoors to share a
    single namespace while the default of None causes them to be separate.
    '''
    serversock = io.Socket()
    serversock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    serversock.bind(address)
    serversock.listen(socket.SOMAXCONN)

    while 1:
        clientsock, address = serversock.accept()
        scheduler.schedule(backdoor_handler, args=(clientsock, locals_))


def backdoor_handler(clientsock, locals_=None):
    '''start a backdoor interpreter on an existing connection

    this function effectively takes over the coroutine it is started in,
    blocking for input over the socket and acting on it until the connection
    is closed

    locals_ is optionally a dictionary that will serve as the execution context
    for the interpreter-over-socket
    '''
    console = code.InteractiveConsole(locals_ or {})
    clientfile = clientsock.makefile('r')
    multiline_statement = []
    stdout, stderr = StringIO(), StringIO()

    clientsock.sendall(PREAMBLE + "\n" + PS1)

    for input_line in clientsock.makefile('r'):
        input_line = input_line.rstrip()
        source = '\n'.join(multiline_statement) + input_line

        with _wrap_stdio(stdout, stderr):
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
