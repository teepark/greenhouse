import os

from greenhouse.io.files import File


def pipe():
    r, w = os.pipe()
    return File.fromfd(r, 'rb'), File.fromfd(w, 'wb')
