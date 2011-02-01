=======================================================
:mod:`greenhouse.emulation` -- Faking Out Third Parties
=======================================================

.. module:: greenhouse.emulation
.. moduleauthor:: Travis J Parker <travis.parker@gmail.com>


Many of the APIs in greenhouse (particularly in the :mod:`greenhouse.utils`
module) have been explicitly made to match the signatures and behavior of IO
and threading related APIs from the standard library. This module enables
monkeypatching the standard libary modules to swap in the greenhouse versions,
the idea being that you can cause a third-party library to use coroutines
without it having to have been explicitly written that way.


.. function:: patch(\*module_names)

    Applies patching to the named standard library modules by importing and
    replacing the relevant attributes on the modules whose names are the
    strings in ``module_names``. With no arguments, applies patching to
    everything it can.

    Valid arguments are ``"__builtin__"``, ``"socket"``, ``"thread"``,
    ``"threading"``, ``"Queue"``, ``"sys"``, ``"select"``, ``"os"``,
    ``"time"``.

    Raises a ``ValueError`` if anything else is provided.

    Note that lots of other standard library modules will work cooperatively as
    a result of patching the ones above -- for example after patching ``os``
    and ``select``, the ``subprocess`` module works cooperatively with no
    further modifications, and by patching just ``socket``, the modules
    ``httplib``, ``urllib``, and ``urllib2`` work cooperatively as well.

.. function:: unpatch(\*module_names)

    Like :func:`patch`, but does the reverse operation returning standard
    library modules to their original state.

    Also raises ``ValueError`` for unrecognized arguments, and unpatches
    everything with no arguments.

.. function:: patched(module_name)

    Applies patching to the standard library just to import the named module,
    then puts everything else back as it was -- this way the only module
    affected will be the specifically named one.

    Patches applied globally by :func:`patch` will not affect or be affected by
    using this.
