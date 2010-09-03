=======================================================
:mod:`greenhouse.emulation` -- Faking Out Third Parties
=======================================================

.. module:: greenhouse.emulation
.. moduleauthor:: Travis J Parker <travis.parker@gmail.com>


Many of the APIs in greenhouse (particularly in the :mod:`greenhouse.utils`
module) have been explicitly made to match the signatures and behavior of IO
and threading related APIs from the standard library. This module provides
enables monkeypatching the standard libary modules to swap in the greenhouse
versions, the idea being that you can cause a third-party library to use
coroutines without it having to have been explicitly written that way.


.. function:: enable(builtins=1, socket=1, thread=1, threading=1, queue=1)

    Just a shortcut for enabling emulation in all the supported stdlib modules.
    It defaults to enabling everything available, but they can be turned off
    individually with the keyword arguments.

.. function:: disable(builtins=1, socket=1, thread=1, threading=1, queue=1)

    A shortcut for disabling emulation across the board. Defaults to affecting
    everything, but individual modules can be left alone with the keyword
    arguments.

.. function:: builtins(enable=True)

    Override blocking APIs in the builtins with their greenhouse
    coroutine-blocking equivalents (currently ``open`` and ``file``).
    
    With ``enable=False``, sets things back to the originals.

.. function:: socket(enable=True)

    Override blocking APIs in the standard library ``socket`` module. So far
    this affects ``socket``, ``socketpair``, and ``fromfd``.
    
    With ``enable=False``, restores the socket module to its original state.

.. function:: thread(enable=True)

    Override thread and blocking APIs in the stdlib ``thread`` module. This
    affects ``allocate``/``allocate_lock`` and
    ``start_new``/``start_new_thread``.

    With ``enable=False``, restores them to the originals.

.. function:: threading(enable=True)

    Override thread and blocking APIs in the stdlib ``threading`` module. This
    affects ``active_count``/``activeCount``,
    ``current_thread``/``currentThread``, ``Event``, ``Lock``, ``RLock``,
    ``Condition``, ``Semaphore``, ``BoundedSemaphore``, ``Timer``, ``Thread``,
    ``local``, and ``enumerate``.
    
    With ``enable=False``, restores the originals.

.. function:: queue(enable=True)

    Override ``Queue.Queue`` with the greenhouse coroutine-blocking equivalent
    :class:`greenhouse.utils.Queue`.

    With ``enable=False``, reverts back to the original.
