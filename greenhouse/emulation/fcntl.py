from __future__ import absolute_import

import errno
import fcntl
import functools

from .. import scheduler


TIMEOUT = 0.01

original_flock = fcntl.flock
original_lockf = fcntl.lockf
original_fcntl = fcntl.fcntl


@functools.wraps(original_flock)
def green_flock(fd, operation):
    # pass unlocks and non-blocking acquires straight through
    if operation & (fcntl.LOCK_NB | fcntl.LOCK_UN):
        return original_flock(fd, operation)

    # doing a blocking lock acquire - fake the blocking
    while 1:
        try:
            return original_flock(fd, operation | fcntl.LOCK_NB)
        except EnvironmentError, exc:
            if exc.args[0] not in (errno.EACCES, errno.EAGAIN):
                raise
            scheduler.pause_for(TIMEOUT)

@functools.wraps(original_lockf)
def green_lockf(fd, operation, length=0, start=0, whence=0):
    # pass unlocks and non-blocking acquires straight through
    if operation & (fcntl.LOCK_NB | fcntl.LOCK_UN):
        return original_lockf(fd, operation, length, start, whence)

    # doing a blocking lock acquire - fake the blocking
    while 1:
        try:
            return original_lockf(fd, operation | fcntl.LOCK_NB,
                                  length, start, whence)
        except EnvironmentError, exc:
            if exc.args[0] not in (errno.EACCES, errno.EAGAIN):
                raise
            scheduler.pause_for(TIMEOUT)

@functools.wraps(original_fcntl)
def green_fcntl(fd, opt, arg=0):
    # pass non-blocking calls straight through
    if opt != fcntl.F_SETLKW:
        return original_fcntl(fd, opt, arg)

    # doing a blocking lock acquire - fake the blocking
    while 1:
        try:
            return original_fcntl(fd, fcntl.F_SETLK, arg)
        except EnvironmentError, exc:
            if exc.args not in (errno.EACCES, errno.EAGAIN):
                raise
            scheduler.pause_for(TIMEOUT)


patchers = {
    'flock': green_flock,
    'lockf': green_lockf,
    'fcntl': green_fcntl,
}
