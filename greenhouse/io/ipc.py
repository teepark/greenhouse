from __future__ import absolute_import

import os

from .files import File


__all__ = ["pipe"]


def pipe():
    """create an inter-process communication pipe

    :returns:
        a pair of :class:`File` objects ``(read, write)`` for the two ends of
        the pipe
    """
    r, w = os.pipe()
    return File.fromfd(r, 'rb'), File.fromfd(w, 'wb')
