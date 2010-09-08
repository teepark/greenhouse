import socket as socket_module
import thread as thread_module
import threading as threading_module
import Queue as queue_module

from greenhouse import compat, io, scheduler, utils


__all__ = [
        "enable",
        "disable",
        "builtins",
        "socket",
        "thread",
        "threading",
        "queue"]


def enable(use_builtins=1, use_socket=1, use_thread=1,
        use_threading=1, use_queue=1):
    if use_builtins:
        builtins()
    if use_socket:
        socket()
    if use_thread:
        thread()
    if use_threading:
        threading()
    if use_queue:
        queue()


def disable(use_builtins=1, use_socket=1, use_thread=1,
        use_threading=1, use_queue=1):
    if use_builtins:
        builtins(enable=False)
    if use_socket:
        socket(enable=False)
    if use_thread:
        thread(enable=False)
    if use_threading:
        threading(enable=False)
    if use_queue:
        queue(enable=False)


def builtins(enable=True):
    if enable:
        __builtins__['open'] = __builtins__['file'] = io.File
    else:
        __builtins__['open'] = io.files._open
        __builtins__['file'] = io.files._file


_default_sockpair_family = socket_module.AF_INET
if hasattr(socket_module, "AF_UNIX"):
    _default_sockpair_family = socket_module.AF_UNIX

def _green_socketpair(*args, **kwargs):
    a, b = io.sockets._socketpair(*args, **kwargs)
    return io.Socket(fromsock=a), io.Socket(fromsock=b)

def socket(enable=True):
    if enable:
        socket_module.socket = io.sockets.Socket
        socket_module.socketpair = _green_socketpair
        socket_module.fromfd = io.sockets.socket_fromfd
    else:
        socket_module.socket = io.sockets._socket
        socket_module.socketpair = io.sockets._socketpair
        socket_module.fromfd = io.sockets._fromfd


_allocate_lock = thread_module.allocate_lock
_allocate = thread_module.allocate
_start_new_thread = thread_module.start_new_thread
_start_new = thread_module.start_new

def _green_start(function, args, kwargs=None):
    glet = compat.greenlet(
            lambda: function(*args, **(kwargs or {})),
            scheduler.state.mainloop)
    scheduler.schedule(glet)
    return id(glet)

def thread(enable=True):
    if enable:
        thread_module.allocate_lock = thread_module.allocate = utils.Lock
        thread_module.start_new_thread = thread_module.start_new = _green_start
    else:
        thread_module.allocate_lock = _allocate_lock
        thread_module.allocate = _allocate
        thread_module.start_new_thread = _start_new_thread
        thread_module.start_new = _start_new


_event = threading_module.Event
_lock = threading_module.Lock
_rlock = threading_module.RLock
_condition = threading_module.Condition
_semaphore = threading_module.Semaphore
_boundedsemaphore = threading_module.BoundedSemaphore
_timer = threading_module.Timer
_thread = threading_module.Thread
_local = threading_module.local
_enumerate = threading_module.enumerate
_active_count = threading_module.active_count
_activeCount = threading_module.activeCount
_current_thread = threading_module.current_thread
_currentThread = threading_module.currentThread

def threading(enable=True):
    if enable:
        threading_module.Event = utils.Event
        threading_module.Lock = utils.Lock
        threading_module.RLock = utils.RLock
        threading_module.Condition = utils.Condition
        threading_module.Semaphore = utils.Semaphore
        threading_module.BoundedSemaphore = utils.BoundedSemaphore
        threading_module.Timer = utils.Timer
        threading_module.Thread = utils.Thread
        threading_module.local = utils.Local
        threading_module.enumerate = utils._enumerate_threads
        threading_module.active_count = utils._active_thread_count
        threading_module.activeCount = utils._active_thread_count
        threading_module.current_thread = utils._current_thread
        threading_module.currentThread = utils._current_thread
    else:
        threading_module.Event = _event
        threading_module.Lock = _lock
        threading_module.RLock = _rlock
        threading_module.Condition = _condition
        threading_module.Semaphore = _semaphore
        threading_module.BoundedSemaphore = _boundedsemaphore
        threading_module.Timer = _timer
        threading_module.Thread = _thread
        threading_module.local = _local
        threading_module.enumerate = _enumerate
        threading_module.active_count = _active_count
        threading_module.activeCount = _activeCount
        threading_module.current_thread = _current_thread
        threading_module.currentThread = _currentThread


_queue = queue_module.Queue

def queue(enable=True):
    if enable:
        queue_module.Queue = utils.Queue
    else:
        queue_module.Queue = _queue
