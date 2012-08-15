from __future__ import absolute_import

from . import descriptor, files, ipc, sockets, ssl


__all__ = ["Socket", "File", "pipe", "stdin", "stdout", "stderr", "wait_fds",
        "SSLSocket", "wrap_socket"]


File = files.File
stdin = files.stdin
stdout = files.stdout
stderr = files.stderr

pipe = ipc.pipe

Socket = sockets.Socket

wait_fds = descriptor.wait_fds

wrap_socket = SSLSocket = ssl.SSLSocket
