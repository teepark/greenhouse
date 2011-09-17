from __future__ import absolute_import

from .. import scheduler, util


def green_start(function, args, kwargs=None):
    glet = scheduler.greenlet(function, args, kwargs)
    scheduler.schedule(glet)
    return id(glet)


thread_patchers = {
    'allocate_lock': util.Lock,
    'allocate': util.Lock,
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
}
