from __future__ import absolute_import

import errno
import fcntl
import functools
import os
import sys

from .. import io, scheduler


OS_TIMEOUT = 0.01


def nonblocking_fd(fd):
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    if not flags & os.O_NONBLOCK:
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    return flags


original_os_read = os.read
original_os_write = os.write
original_os_waitpid = os.waitpid
original_os_wait = os.wait
original_os_wait3 = os.wait3
original_os_wait4 = os.wait4
original_os_popen = os.popen
original_os_popen2 = os.popen2
original_os_popen3 = os.popen3
original_os_popen4 = os.popen4
original_os_system = os.system
original_os_spawnl = os.spawnl
original_os_spawnle = os.spawnle
original_os_spawnlp = os.spawnlp
original_os_spawnlpe = os.spawnlpe
original_os_spawnv = os.spawnv
original_os_spawnve = os.spawnve
original_os_spawnvp = os.spawnvp
original_os_spawnvpe = os.spawnvpe

def green_read(fd, buffsize):
    flags = nonblocking_fd(fd)
    if flags & os.O_NONBLOCK:
        return original_os_read(fd, buffsize)

    try:
        while 1:
            try:
                return original_os_read(fd, buffsize)
            except EnvironmentError, exc:
                if exc.args[0] != errno.EAGAIN:
                    raise
                io.wait_fds([(fd, 1)])
    finally:
        if not flags & os.O_NONBLOCK:
            fcntl.fcntl(fd, fcntl.F_SETFL, flags)

def green_write(fd, data):
    flags = nonblocking_fd(fd)
    if flags & os.O_NONBLOCK:
        return original_os_write(fd, data)

    try:
        while 1:
            try:
                return original_os_write(fd, data)
            except EnvironmentError, exc:
                if exc.args[0] != errno.EAGAIN:
                    raise
                io.wait_fds([(fd, 2)])
    finally:
        if not flags & os.O_NONBLOCK:
            fcntl.fcntl(fd, fcntl.F_SETFL, flags)

def blocking_read(fd, buffsize):
    nonblocking_fd(fd)
    while 1:
        try:
            return original_os_read(fd, buffsize)
        except EnvironmentError, exc:
            if exc.args[0] != errno.EAGAIN:
                raise
            io.wait_fds([(fd, 1)])

def blocking_write(fd, data):
    nonblocking_fd(fd)
    while 1:
        try:
            return original_os_write(fd, data)
        except EnvironmentError, exc:
            if exc.args[0] != errno.EAGAIN:
                raise
            io.wait_fds([(fd, 2)])

def polling_green_version(func, retry_test, opt_arg_num, arg_count, timeout):
    @functools.wraps(func)
    def green_version(*args):
        if len(args) < arg_count:
            raise TypeError("%s takes %d arguments" % (
                func.__name__, arg_count))

        options = args[opt_arg_num]
        if options & os.WNOHANG:
            return func(*args)

        args = list(args)
        args[opt_arg_num] = options | os.WNOHANG
        while 1:
            result = func(*args)
            if not retry_test(result):
                return result
            scheduler.pause_for(timeout)

    return green_version

green_waitpid = polling_green_version(
        original_os_waitpid, lambda x: not (x[0] or x[1]), 1, 2, OS_TIMEOUT)
green_wait3 = polling_green_version(
        original_os_wait3, lambda x: not (x[0] or x[1]), 0, 1, OS_TIMEOUT)
green_wait4 = polling_green_version(
        original_os_wait4, lambda x: not (x[0] or x[1]), 1, 2, OS_TIMEOUT)

@functools.wraps(original_os_wait)
def green_wait():
    return green_waitpid(0, 0)

class green_popen_pipe(io.File):
    @classmethod
    def fromfd(cls, fd, mode, pid):
        fp = super(green_popen_pipe, cls).fromfd(fd, mode)
        fp._pid = pid
        return fp

    def close(self):
        super(green_popen_pipe, self).close()
        return green_waitpid(self._pid, 0)[1] or None

@functools.wraps(original_os_popen)
def green_popen(cmd, mode='r', bufsize=-1):
    if 'r' in mode:
        pipe = 'stdout'
    if 'w' in mode:
        pipe = 'stderr'
    kwarg = {pipe: green_subprocess.PIPE}

    proc = green_subprocess.Popen(cmd, shell=1, bufsize=bufsize, **kwarg)
    return green_popen_pipe.fromfd(getattr(proc, pipe), mode, proc.pid)

@functools.wraps(original_os_popen2)
def green_popen2(cmd, mode='r', bufsize=-1):
    proc = green_subprocess.Popen(cmd, shell=1, bufsize=bufsize,
            stdin=green_subprocess.PIPE, stdout=green_subprocess.PIPE)
    return proc.stdin, proc.stdout

@functools.wraps(original_os_popen3)
def green_popen3(cmd, mode='r', bufsize=-1):
    proc = green_subprocess.Popen(cmd, shell=1, bufsize=bufsize,
            stdin=green_subprocess.PIPE, stdout=green_subprocess.PIPE,
            stderr=green_subprocess.PIPE)
    return proc.stdin, proc.stdout, proc.stderr

@functools.wraps(original_os_popen4)
def green_popen4(cmd, mode='r', bufsize=-1):
    proc = green_subprocess.Popen(cmd, shell=1, bufsize=bufsize,
            stdin=green_subprocess.PIPE, stdout=green_subprocess.PIPE,
            stderr=green_subprocess.STDOUT)
    return proc.stdin, proc.stdout

@functools.wraps(original_os_system)
def green_system(cmd):
    return green_waitpid(green_subprocess.Popen(cmd, shell=1).pid, 0)[1]

def green_spawner(func):
    @functools.wraps(func)
    def green_version(mode, *args):
        if mode != os.P_WAIT:
            return func(mode, *args)

        pid = func(os.P_NOWAIT, *args)
        details = green_waitpid(pid, 0)[1]

        if details & 0xff:
            return -(details & 0xff)
        return details >> 8

green_spawnl = green_spawner(original_os_spawnl)
green_spawnle = green_spawner(original_os_spawnle)
green_spawnlp = green_spawner(original_os_spawnlp)
green_spawnlpe = green_spawner(original_os_spawnlpe)
green_spawnv = green_spawner(original_os_spawnv)
green_spawnve = green_spawner(original_os_spawnve)
green_spawnvp = green_spawner(original_os_spawnvp)
green_spawnvpe = green_spawner(original_os_spawnvpe)

is_pypy = sys.subversion[0].lower() == 'pypy'

patchers = {
    'fdopen': io.File.fromfd,
    'read': is_pypy and blocking_read or green_read,
    'write': is_pypy and blocking_write or green_write,
    'waitpid': green_waitpid,
    'wait': green_wait,
    'wait3': green_wait3,
    'wait4': green_wait4,
    'popen': green_popen,
    'popen2': green_popen2,
    'popen3': green_popen3,
    'popen4': green_popen4,
    'system': green_system,
    'spawnl': green_spawnl,
    'spawnle': green_spawnle,
    'spawnlp': green_spawnlp,
    'spawnlpe': green_spawnlpe,
    'spawnv': green_spawnv,
    'spawnve': green_spawnve,
    'spawnvp': green_spawnvp,
    'spawnvpe': green_spawnvpe,
}
