from greenhouse import io, scheduler, utils


__all__ = ["patch", "unpatch"]


def _green_socketpair(*args, **kwargs):
    a, b = io.sockets._socketpair(*args, **kwargs)
    return io.Socket(fromsock=a), io.Socket(fromsock=b)

def _green_start(function, args, kwargs=None):
    glet = scheduler.greenlet(function, args, kwargs)
    scheduler.schedule(glet)
    return id(glet)


_patchers = {
    'socket': {
        'socket': io.sockets.Socket,
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
    },
}

_standard = {'builtins': {'file': file, 'open': open}}
for mod_name, patchers in _patchers.items():
    _standard[mod_name] = {}
    module = __import__(mod_name)
    for attr_name, patcher in patchers.items():
        _standard[mod_name][attr_name] = getattr(module, attr_name)
del mod_name, patchers, module, attr_name, patcher

_patchers['builtins'] = {'file': io.File, 'open': io.File}


def patch(*module_names):
    if not module_names:
        module_names = _patchers.keys()

    for module_name in module_names:
        if module_name not in _patchers:
            raise ValueError("'%s' is not greenhouse-patchable" % module_name)

    for module_name in module_names:
        if module_name == "builtins":
            for attr, patch in _patchers['builtins'].items():
                __builtins__[attr] = patch
        else:
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
        if module_name == "builtins":
            for attr, value in _standard['builtins'].items():
                __builtins__[attr] = value
        else:
            module = __import__(module_name)
            for attr, value in _standard[module_name].items():
                setattr(module, attr, value)
