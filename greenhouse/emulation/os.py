from __future__ import absolute_import

import errno
import fcntl
import functools
import os

from .. import io, scheduler


OS_TIMEOUT = 0.001


def _nonblocking_fd(fd):
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    if flags & os.O_NONBLOCK:
        return True, flags
    fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    return False, flags


_original_os_read = os.read
_original_os_write = os.write
_original_os_waitpid = os.waitpid
_original_os_wait = os.wait
_original_os_wait3 = os.wait3
_original_os_wait4 = os.wait4
_original_os_popen = os.popen
_original_os_popen2 = os.popen2
_original_os_popen3 = os.popen3
_original_os_popen4 = os.popen4
_original_os_system = os.system
_original_os_spawnl = os.spawnl
_original_os_spawnle = os.spawnle
_original_os_spawnlp = os.spawnlp
_original_os_spawnlpe = os.spawnlpe
_original_os_spawnv = os.spawnv
_original_os_spawnve = os.spawnve
_original_os_spawnvp = os.spawnvp
_original_os_spawnvpe = os.spawnvpe

def _green_read(fd, buffsize):
    nonblocking, flags = _nonblocking_fd(fd)
    if nonblocking:
        return _original_os_read(fd, buffsize)

    try:
        while 1:
            try:
                return _original_os_read(fd, buffsize)
            except EnvironmentError, exc:
                if exc.args[0] != errno.EAGAIN:
                    raise
                io.wait_fds([(fd, 1)])
    finally:
        if not nonblocking:
            fcntl.fcntl(fd, fcntl.F_SETFL, flags)

def _green_write(fd, data):
    nonblocking, flags = _nonblocking_fd(fd)
    if nonblocking:
        return _original_os_write(fd, data)

    try:
        while 1:
            try:
                return _original_os_write(fd, data)
            except EnvironmentError, exc:
                if exc.args[0] != errno.EAGAIN:
                    raise
                io.wait_fds([(fd, 2)])
    finally:
        if not nonblocking:
            fcntl.fcntl(fd, fcntl.F_SETFL, flags)

def _polling_green_version(func, retry_test, opt_arg_num, arg_count, timeout):
    @functools.wraps(func)
    def _green_version(*args):
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

    return _green_version

_green_waitpid = _polling_green_version(
        _original_os_waitpid, lambda x: not (x[0] or x[1]), 1, 2, OS_TIMEOUT)
_green_wait3 = _polling_green_version(
        _original_os_wait3, lambda x: not (x[0] or x[1]), 0, 1, OS_TIMEOUT)
_green_wait4 = _polling_green_version(
        _original_os_wait4, lambda x: not (x[0] or x[1]), 1, 2, OS_TIMEOUT)

@functools.wraps(_original_os_wait)
def _green_wait():
    return _green_waitpid(0, 0)

class _green_popen_pipe(io.File):
    @classmethod
    def fromfd(cls, fd, mode, pid):
        fp = super(_green_popen_pipe, cls).fromfd(fd, mode)
        fp._pid = pid
        return fp

    def close(self):
        super(_green_popen_pipe, self).close()
        return _green_waitpid(self._pid, 0)[1] or None

@functools.wraps(_original_os_popen)
def _green_popen(cmd, mode='r', bufsize=-1):
    if 'r' in mode:
        pipe = 'stdout'
    if 'w' in mode:
        pipe = 'stderr'
    kwarg = {pipe: _green_subprocess.PIPE}

    proc = _green_subprocess.Popen(cmd, shell=1, bufsize=bufsize, **kwarg)
    return _green_popen_pipe.fromfd(getattr(proc, pipe), mode, proc.pid)

@functools.wraps(_original_os_popen2)
def _green_popen2(cmd, mode='r', bufsize=-1):
    proc = _green_subprocess.Popen(cmd, shell=1, bufsize=bufsize,
            stdin=_green_subprocess.PIPE, stdout=_green_subprocess.PIPE)
    return proc.stdin, proc.stdout

@functools.wraps(_original_os_popen3)
def _green_popen3(cmd, mode='r', bufsize=-1):
    proc = _green_subprocess.Popen(cmd, shell=1, bufsize=bufsize,
            stdin=_green_subprocess.PIPE, stdout=_green_subprocess.PIPE,
            stderr=_green_subprocess.PIPE)
    return proc.stdin, proc.stdout, proc.stderr

@functools.wraps(_original_os_popen4)
def _green_popen4(cmd, mode='r', bufsize=-1):
    proc = _green_subprocess.Popen(cmd, shell=1, bufsize=bufsize,
            stdin=_green_subprocess.PIPE, stdout=_green_subprocess.PIPE,
            stderr=_green_subprocess.STDOUT)
    return proc.stdin, proc.stdout

@functools.wraps(_original_os_system)
def _green_system(cmd):
    return _green_waitpid(_green_subprocess.Popen(cmd, shell=1).pid, 0)[1]

def _green_spawner(func):
    @functools.wraps(func)
    def green_version(mode, *args):
        if mode != os.P_WAIT:
            return func(mode, *args)

        pid = func(os.P_NOWAIT, *args)
        details = _green_waitpid(pid, 0)[1]

        if details & 0xff:
            return -(details & 0xff)
        return details >> 8

_green_spawnl = _green_spawner(_original_os_spawnl)
_green_spawnle = _green_spawner(_original_os_spawnle)
_green_spawnlp = _green_spawner(_original_os_spawnlp)
_green_spawnlpe = _green_spawner(_original_os_spawnlpe)
_green_spawnv = _green_spawner(_original_os_spawnv)
_green_spawnve = _green_spawner(_original_os_spawnve)
_green_spawnvp = _green_spawner(_original_os_spawnvp)
_green_spawnvpe = _green_spawner(_original_os_spawnvpe)


_os_patchers = {
    'fdopen': io.File.fromfd,
    'read': _green_read,
    'write': _green_write,
    'waitpid': _green_waitpid,
    'wait': _green_wait,
    'wait3': _green_wait3,
    'wait4': _green_wait4,
    'popen': _green_popen,
    'popen2': _green_popen2,
    'popen3': _green_popen3,
    'popen4': _green_popen4,
    'system': _green_system,
    'spawnl': _green_spawnl,
    'spawnle': _green_spawnle,
    'spawnlp': _green_spawnlp,
    'spawnlpe': _green_spawnlpe,
    'spawnv': _green_spawnv,
    'spawnve': _green_spawnve,
    'spawnvp': _green_spawnvp,
    'spawnvpe': _green_spawnvpe,
}
