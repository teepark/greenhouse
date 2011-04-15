"""monkey-patching facilities for greenhouse's  cooperative stdlib replacements

many of the apis in greenhouse (particularly in the :mod:`greenhouse.utils`
module) have been explicitly made to match the signatures and behavior of I/O
and threading related apis from the python standard library.

this module enables monkey-patching the stdlib modules to swap in the
greenhouse versions, the idea being that you can cause a third-party library to
use coroutines without it having to be explicitly written that way.
"""
from __future__ import absolute_import

import sys
import types

from .. import io, scheduler, utils


__all__ = ["patch", "unpatch", "patched"]


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


def _patched_copy(mod_name, patch):
    old_mod = __import__(mod_name, {}, {}, mod_name.rsplit(".", 1)[0])
    new_mod = types.ModuleType(old_mod.__name__)
    new_mod.__dict__.update(old_mod.__dict__)
    new_mod.__dict__.update(patch)
    return new_mod


# the definitive list of which attributes of which modules get monkeypatched
# (this gets added to with submodule imports below)
_patchers = {
    '__builtin__': {
        'file': io.File,
        'open': io.File,
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

    'time': {
        'sleep': scheduler.pause_for,
    }
}


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
            print "patching %s.%s" % (module_name, attr)
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


from . import select
_patchers['select'] = select._select_patchers

from . import socket
_patchers['socket'] = socket._socket_patchers

from . import threading
_patchers['thread'] = threading._thread_patchers
_patchers['threading'] = threading._threading_patchers

from . import os
# implementing child process-related
# things in the os module in terms of this
os._green_subprocess = patched('subprocess')

from . import zmq
if zmq._zmq_patchers:
    _patchers['zmq'] = zmq._zmq_patchers
    _patchers['zmq.core'] = zmq._zmq_core_patchers
    _patchers['zmq.core.context'] = zmq._zmq_core_context_patchers
    _patchers['zmq.core.socket'] = zmq._zmq_core_socket_patchers
    _patchers['zmq.core.poll'] = zmq._zmq_core_poll_patchers

try:
    dns_exception = patched("dns.exception")
    dns_resolver = patched("dns.resolver")
    dns_rdatatype = patched("dns.rdatatype")
    dns_reversename = patched("dns.reversename")

    from . import dns

    dns.dns_exception = dns_exception
    dns.dns_resolver = dns_resolver
    dns.dns_rdatatype = dns_rdatatype
    dns.dns_reversename = dns_reversename

    _patchers['socket'].update(dns._dns_socket_patchers)

except ImportError:
    pass


_standard = {}
for mod_name, patchers in _patchers.items():
    _standard[mod_name] = {}

    module = __import__(mod_name, {}, {}, mod_name.rsplit(".", 1)[0])
    for attr_name, patcher in patchers.items():
        _standard[mod_name][attr_name] = getattr(module, attr_name, None)
del mod_name, patchers, module, attr_name, patcher
