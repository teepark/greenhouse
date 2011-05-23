from __future__ import absolute_import

from . import descriptor, files, ipc, sockets


__all__ = ["Socket", "File", "pipe", "stdin", "stdout", "stderr", "wait_fds"]


File = files.File
stdin = files.stdin
stdout = files.stdout
stderr = files.stderr

pipe = ipc.pipe

Socket = sockets.Socket

wait_fds = descriptor.wait_fds
