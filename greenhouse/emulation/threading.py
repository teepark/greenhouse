from __future__ import absolute_import

from .. import scheduler, utils


def green_start(function, args, kwargs=None):
    glet = scheduler.greenlet(function, args, kwargs)
    scheduler.schedule(glet)
    return id(glet)


thread_patchers = {
    'allocate_lock': utils.Lock,
    'allocate': utils.Lock,
    'start_new_thread': green_start,
    'start_new': green_start,
}


threading_patchers = {
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
}
