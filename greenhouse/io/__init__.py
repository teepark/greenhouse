from greenhouse.io import files, ipc, sockets


__all__ = ["Socket", "File", "pipe", "stdin", "stdout", "stderr"]


File = files.File
stdin = files.stdin
stdout = files.stdout
stderr = files.stderr

pipe = ipc.pipe

Socket = sockets.Socket
