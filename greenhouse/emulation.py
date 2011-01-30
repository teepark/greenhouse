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

def patch(*module_names):
    if not module_names:
        module_names = _patchers.keys()

    for module_name in module_names:
        if module_name not in _patchers:
            raise ValueError("'%s' is not greenhouse-patchable" % module_name)

    for module_name in module_names:
        module = __import__(module_name)
        for attr, patch in _patchers[module_name].items():
            setattr(module, attr, patch)


def unpatch(*module_names):
    if not module_names:
        module_names = _standard.keys()

    for module_name in module_names:
        if module_name not in _standard:
            raise ValueError("'%s' is not greenhouse-patchable" % module_name)

    for module_name in module_names:
        module = __import__(module_name)
        for attr, value in _standard[module_name].items():
            setattr(module, attr, value)


def _patched_copy(mod_name, patch):
    old_mod = __import__(mod_name, {}, {}, mod_name.rsplit(".")[0])
    new_mod = types.ModuleType(old_mod.__name__)
    new_mod.__dict__.update(old_mod.__dict__)
    new_mod.__dict__.update(patch)
    return new_mod


def patched(module_name):
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
    result = __import__(module_name, {}, {}, module_name.rsplit(".")[0])

    # put all the original modules back as they were
    for name, old_mod in saved:
        if old_mod is None:
            sys.modules.pop(name)
        else:
            sys.modules[name] = old_mod

    return result


def _green_select(rlist, wlist, xlist, timeout=None):
    fds = {}
    for fd in rlist:
        fd = fd if isinstance(fd, int) else fd.fileno()
        fds[fd] = 1

    for fd in wlist:
        fd = fd if isinstance(fd, int) else fd.fileno()
        if fd in fds:
            fds[fd] |= 2
        else:
            fds[fd] = 2

    events = io.wait_fds(fds.items(), timeout=timeout, inmask=1, outmask=2)

    rlist_out, wlist_out = [], []
    for fd, event in events:
        if event & 1:
            rlist_out.append(fd)
        if event & 2:
            wlist_out.append(fd)

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
        'read': _green_read,
        'write': _green_write,
        'waitpid': _green_waitpid,
        'wait': _green_wait,
        'wait3': _green_wait3,
        'wait4': _green_wait4,
    },

    'time': {
        'sleep': scheduler.pause_for,
    }
}

_standard = {}
for mod_name, patchers in _patchers.items():
    _standard[mod_name] = {}
    module = __import__(mod_name)
    for attr_name, patcher in patchers.items():
        _standard[mod_name][attr_name] = getattr(module, attr_name, None)
del mod_name, patchers, module, attr_name, patcher

# implementing child process-related things in
# the os/popen2/command modules in terms of this
_green_subprocess = patched('subprocess')
