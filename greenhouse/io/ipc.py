import os

from greenhouse.io.files import File


__all__ = ["pipe"]


def pipe():
    r, w = os.pipe()
    return File.fromfd(r, 'rb'), File.fromfd(w, 'wb')
