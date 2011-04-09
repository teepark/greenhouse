"""monkey-patching facilities for greenhouse's  cooperative stdlib replacements

many of the apis in greenhouse (particularly in the :mod:`greenhouse.utils`
module) have been explicitly made to match the signatures and behavior of I/O
and threading related apis from the python standard library.

this module enables monkey-patching the stdlib modules to swap in the
greenhouse versions, the idea being that you can cause a third-party library to
use coroutines without it having to be explicitly written that way.
"""

import errno
import fcntl
import functools
import os
import select
import sys
import types
import weakref

from greenhouse import compat, io, scheduler, utils


__all__ = ["patch", "unpatch", "patched"]


OS_TIMEOUT = 0.001


def _green_select(rlist, wlist, xlist, timeout=None):
    robjs = {}
    wobjs = {}
    fds = {}

    for fd in rlist:
        fdnum = fd if isinstance(fd, int) else fd.fileno()
        robjs[fdnum] = fd
        fds[fdnum] = 1

    for fd in wlist:
        fdnum = fd if isinstance(fd, int) else fd.fileno()
        wobjs[fdnum] = fd
        if fdnum in fds:
            fds[fdnum] |= 2
        else:
            fds[fdnum] = 2

    events = io.wait_fds(fds.items(), timeout=timeout, inmask=1, outmask=2)

    rlist_out, wlist_out = [], []
    for fd, event in events:
        if event & 1:
            rlist_out.append(robjs[fd])
        if event & 2:
            wlist_out.append(wobjs[fd])

    return rlist_out, wlist_out, []

_select_patchers = {'select': _green_select}


class _green_poll(object):
    def __init__(self):
        self._registry = {}

    def modify(self, fd, eventmask):
        fd = fd if isinstance(fd, int) else fd.fileno()
        if fd not in self._registry:
            raise IOError(2, "No such file or directory")
        self._registry[fd] = eventmask

    def poll(self, timeout=None):
        if timeout is not None:
            timeout = float(timeout) / 1000
        return io.wait_fds(self._registry.items(), timeout=timeout,
                inmask=select.POLLIN, outmask=select.POLLOUT)

    def register(self, fd, eventmask):
        fd = fd if isinstance(fd, int) else fd.fileno()
        self._registry[fd] = eventmask

    def unregister(self, fd):
        fd = fd if isinstance(fd, int) else fd.fileno()
        del self._registry[fd]

if hasattr(select, "poll"):
    _select_patchers['poll'] = _green_poll


class _green_epoll(object):
    def __init__(self, from_ep=None):
        self._readable = utils.Event()
        self._writable = utils.Event()
        if from_ep:
            self._epoll = from_ep
        else:
            self._epoll = _original_epoll()
        scheduler.state.descriptormap[self._epoll.fileno()].append(
                weakref.ref(self))

    def close(self):
        self._epoll.close()

    @property
    def closed(self):
        return self._epoll.closed
    _closed = closed

    def fileno(self):
        return self._epoll.fileno()

    @classmethod
    def fromfd(cls, fd):
        return cls(from_ep=select.epoll.fromfd(fd))

    def modify(self, fd, eventmask):
        self._epoll.modify(fd, eventmask)

    def poll(self, timeout=None, maxevents=-1):
        poller = scheduler.state.poller
        reg = poller.register(self._epoll.fileno(), poller.INMASK)
        try:
            self._readable.wait(timeout=timeout)
            return self._epoll.poll(0, maxevents)
        finally:
            poller.unregister(self._epoll.fileno(), reg)

    def register(self, fd, eventmask):
        self._epoll.register(fd, eventmask)

    def unregister(self, fd):
        self._epoll.unregister(fd)

if hasattr(select, "epoll"):
    _select_patchers['epoll'] = _green_epoll
    _original_epoll = select.epoll


class _green_kqueue(object):
    def __init__(self, from_kq=None):
        self._readable = utils.Event()
        self._writable = utils.Event()
        if from_kq:
            self._kqueue = from_kq
        else:
            self._kqueue = select.kqueue()
        scheduler.state.descriptormap[self._kqueue.fileno()].append(
                weakref.ref(self))

    def close(self):
        self._kqueue.close()

    @property
    def closed(self):
        return self._kqueue.closed
    _closed = closed

    def control(self, events, max_events, timeout=None):
        if not max_events:
            return self._kqueue.control(events, max_events, 0)

        poller = scheduler.state.poller
        reg = poller.register(self._kqueue.fileno(), poller.INMASK)
        try:
            self._readable.wait(timeout=timeout)
            return self._kqueue.control(events, max_events, 0)
        finally:
            poller.unregister(self._kqueue.fileno(), reg)

    def fileno(self):
        return self._kqueue.fileno()

    @classmethod
    def fromfd(cls, fd):
        return cls(from_kq=select.kqueue.fromfd(fd))

if hasattr(select, "kqueue"):
    _select_patchers['kqueue'] = _green_kqueue


def _green_socketpair(*args, **kwargs):
    a, b = io.sockets._socketpair(*args, **kwargs)
    return io.Socket(fromsock=a), io.Socket(fromsock=b)


def _green_start(function, args, kwargs=None):
    glet = scheduler.greenlet(function, args, kwargs)
    scheduler.schedule(glet)
    return id(glet)


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


# the definitive list of which attributes of which modules get monkeypatched
_patchers = {
    '__builtin__': {
        'file': io.File,
        'open': io.File,
    },

    'socket': {
        'socket': io.Socket,
        'socketpair': _green_socketpair,
        'fromfd': io.sockets.socket_fromfd,
    },

    'thread': {
        'allocate_lock': utils.Lock,
        'allocate': utils.Lock,
        'start_new_thread': _green_start,
        'start_new': _green_start,
    },

    'threading': {
        'Event': utils.Event,
        'Lock': utils.Lock,
        'RLock': utils.RLock,
        'Condition': utils.Condition,
        'Semaphore': utils.Semaphore,
        'BoundedSemaphore': utils.BoundedSemaphore,
        'Timer': utils.Timer,
        'Thread': utils.Thread,
        'local': utils.Local,
        'enumerate': utils._enumerate_threads,
        'active_count': utils._active_thread_count,
        'activeCount': utils._active_thread_count,
        'current_thread': utils._current_thread,
        'currentThread': utils._current_thread,
    },

    'Queue': {
        'Queue': utils.Queue,
        'LifoQueue': utils.LifoQueue,
        'PriorityQueue': utils.PriorityQueue,
    },

    'sys': {
        'stdin': io.files.stdin,
        'stdout': io.files.stdout,
        'stderr': io.files.stderr,
    },

    'select': _select_patchers,

    'os': {
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
    },

    'time': {
        'sleep': scheduler.pause_for,
    }
}

_standard = {}
for mod_name, patchers in _patchers.items():
    _standard[mod_name] = {}

    module = __import__(mod_name, {}, {}, mod_name.rsplit(".", 1)[0])
    for attr_name, patcher in patchers.items():
        _standard[mod_name][attr_name] = getattr(module, attr_name, None)
del mod_name, patchers, module, attr_name, patcher


def patch(*module_names):
    """apply monkey-patches to stdlib modules in-place

    imports the relevant modules and simply overwrites attributes on the module
    objects themselves. those attributes may be functions, classes or other
    attributes.

    valid arguments are:

    - __builtin__
    - os
    - sys
    - select
    - time
    - thread
    - threading
    - Queue
    - socket

    with no arguments, patches everything it can in all of the above modules

    :raises: ``ValueError`` if an unknown module name is provided

    .. note::
        lots more standard library modules can be made non-blocking by virtue
        of patching some combination of the the above (because they only block
        by using blocking functions defined elsewhere). a few examples:

        - ``subprocess`` works cooperatively with ``os`` and ``select`` patched
        - ``httplib``, ``urllib`` and ``urllib2`` will all operate
          cooperatively with ``socket`` patched
    """
    if not module_names:
        module_names = _patchers.keys()

    for module_name in module_names:
        if module_name not in _patchers:
            raise ValueError("'%s' is not greenhouse-patchable" % module_name)

    for module_name in module_names:
        module = __import__(module_name, {}, {}, module_name.rsplit(".", 1)[0])
        for attr, patch in _patchers[module_name].items():
            setattr(module, attr, patch)


def unpatch(*module_names):
    """undo :func:`patch`\es to standard library modules

    this function takes one or more module names and puts back their patched
    attributes to the standard library originals.

    valid arguments are the same as for :func:`patch`.

    with no arguments, undoes all monkeypatches that have been applied

    :raises: ``ValueError`` if an unknown module name is provided
    """
    if not module_names:
        module_names = _standard.keys()

    for module_name in module_names:
        if module_name not in _standard:
            raise ValueError("'%s' is not greenhouse-patchable" % module_name)

    for module_name in module_names:
        module = __import__(module_name, {}, {}, module_name.rsplit(".", 1)[0])
        for attr, value in _standard[module_name].items():
            setattr(module, attr, value)


def _patched_copy(mod_name, patch):
    old_mod = __import__(mod_name, {}, {}, mod_name.rsplit(".", 1)[0])
    new_mod = types.ModuleType(old_mod.__name__)
    new_mod.__dict__.update(old_mod.__dict__)
    new_mod.__dict__.update(patch)
    return new_mod


def patched(module_name):
    """import and return a named module with patches applied locally only

    this function returns a module after importing it in such as way that it
    will operate cooperatively, but not overriding the module globally.

    >>> green_httplib = patched("httplib")
    >>> # using green_httplib will only block greenlets
    >>> import httplib
    >>> # using httplib will block threads/processes
    >>> # both can exist simultaneously

    :param module_name:
        the module's name that is to be imported. this can be a dot-delimited
        name, in which case the module at the end of the path is the one that
        will be returned
    :type module_name: str

    :returns:
        the module indicated by module_name, imported so that it will not block
        globally, but also not touching existing global modules
    """
    if module_name in _patchers:
        return _patched_copy(module_name, _patchers[module_name])

    # grab the unpatched version of the module for posterity
    old_module = sys.modules.pop(module_name, None)

    # apply all the standard library patches we have
    saved = [(module_name, old_module)]
    for name, patch in _patchers.iteritems():
        new_mod = _patched_copy(name, patch)
        saved.append((name, sys.modules.pop(name)))
        sys.modules[name] = new_mod

    # import the requested module with patches in place
    result = __import__(module_name, {}, {}, module_name.rsplit(".", 1)[0])

    # put all the original modules back as they were
    for name, old_mod in saved:
        if old_mod is None:
            sys.modules.pop(name)
        else:
            sys.modules[name] = old_mod

    return result


# implementing child process-related things in
# the os/popen2/command modules in terms of this
_green_subprocess = patched('subprocess')
