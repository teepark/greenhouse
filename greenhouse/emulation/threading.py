from __future__ import absolute_import

# yes, this is an unused import, but stdlib threading.py checks
# `'dummy_import' in sys.modules` when it's deleting the main thread, and
# doesn't re-raise a KeyError in that case. so we just need to ensure that
# dummy_threading gets imported.
import dummy_threading

import thread

from .. import scheduler, util


def green_start(function, args, kwargs=None):
    glet = scheduler.greenlet(function, args, kwargs)
    scheduler.schedule(glet)
    return id(glet)

def thread_exit():
    raise SystemExit()

def thread_get_ident():
    return util._current_thread().ident

def thread_stack_size(size=None):
    if size is not None:
        raise thread.ThreadError()
    # doesn't really apply, but whatever
    return thread.stack_size()


thread_patchers = {
    'allocate_lock': util.Lock,
    'allocate': util.Lock,
    'exit': thread_exit,
    'exit_thread': thread_exit,
    'get_ident': thread_get_ident,
    '_local': util.Local,
    'LockType': util.Lock,
    'stack_size': thread_stack_size,
    'start_new_thread': green_start,
    'start_new': green_start,
}


threading_patchers = {
    'Event': util.Event,
    'Lock': util.Lock,
    'RLock': util.RLock,
    'Condition': util.Condition,
    'Semaphore': util.Semaphore,
    'BoundedSemaphore': util.BoundedSemaphore,
    'Timer': util.Timer,
    'Thread': util.Thread,
    'local': util.Local,
    'enumerate': util._enumerate_threads,
    'active_count': util._active_thread_count,
    'activeCount': util._active_thread_count,
    'current_thread': util._current_thread,
    'currentThread': util._current_thread,
    '_allocate_lock': util.Lock,
    '_sleep': scheduler.pause_for,
    '_start_new_thread': green_start,
    '_active': util.Thread._active_by_id,
}

threading_local_patchers = {
    'RLock': util.RLock,
    'current_thread': util._current_thread,
    'local': util.Local,
}
