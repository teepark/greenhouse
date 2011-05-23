from __future__ import absolute_import

import psycopg2
from psycopg2 import extensions

from ..io import descriptor


__all__ = ["wait_callback"]


def wait_callback(connection):
    """callback function suitable for ``psycopg2.set_wait_callback``

    pass this function to ``psycopg2.set_wait_callack`` to force any blocking
    operations from psycopg2 to only block the current coroutine, rather than
    the entire thread or process

    to undo the change and return to normal blocking operation, use
    `psycopg2.set_wait_callback(None)``
    """
    while 1:
        state = connection.poll()

        if state == extensions.POLL_OK:
            break
        elif state == extensions.POLL_READ:
            descriptor.wait_fds([(connection.fileno(), 1)])
        elif state == extensions.POLL_WRITE:
            descriptor.wait_fds([(connection.fileno(), 2)])
        else:
            raise psycopg2.OperationalError("Bad poll result: %r" % state)
