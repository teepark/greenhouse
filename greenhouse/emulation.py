import sys
import types

from greenhouse import io, scheduler, utils


__all__ = ["patch", "unpatch", "patched"]


def _green_socketpair(*args, **kwargs):
    a, b = io.sockets._socketpair(*args, **kwargs)
    return io.Socket(fromsock=a), io.Socket(fromsock=b)

def _green_start(function, args, kwargs=None):
    glet = scheduler.greenlet(function, args, kwargs)
    scheduler.schedule(glet)
    return id(glet)


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
    },

    'sys': {
        'stdin': io.files.stdin,
        'stdout': io.files.stdout,
        'stderr': io.files.stderr,
    },
}

_standard = {}
for mod_name, patchers in _patchers.items():
    _standard[mod_name] = {}
    module = __import__(mod_name)
    for attr_name, patcher in patchers.items():
        _standard[mod_name][attr_name] = getattr(module, attr_name, None)
del mod_name, patchers, module, attr_name, patcher


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
    saved = []
    for name, patch in _patchers.iteritems():
        new_mod = _patched_copy(name, patch)
        saved.append((name, sys.modules.pop(name)))
        sys.modules[name] = new_mod

    # import the requested module with patches in place
    result = __import__(module_name, {}, {}, module_name.rsplit(".")[0])

    # put the original modules back as they were
    for name, old_mod in saved:
        if old_mod is None:
            sys.modules.pop(name)
        else:
            sys.modules[name] = old_mod

    # and put the old version of this module back
    if old_module is None:
        sys.modules.pop(module_name)
    else:
        sys.modules[module_name] = old_module

    return result
