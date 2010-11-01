========================================================================
:mod:`greenhouse.scheduler` -- Interacting With The Greenhouse Scheduler
========================================================================

.. module:: greenhouse.scheduler
.. moduleauthor:: Travis J Parker <travis.parker@gmail.com>

.. function:: pause()

    Pauses execution of the current greenlet to let others run. This greenlet
    will be picked up in the next iteration of the main scheduler loop.

.. function:: pause_until(unixtime)

    Pauses the current greenlet and does not allow it to be put back into the
    runnable queue until *unixtime* (a unix timestamp int or float).

.. function:: pause_for(seconds)

    Pauses the current greenlet and does not allow it to be put back into the
    runnable queue until *seconds* seconds (int or float) have gone by.

.. function:: schedule(target=None, args=(), kwargs={})

    Creates a new greenlet around *target* (if it is a function) or uses the
    one provided (if *target* is a greenlet), and schedules it such that it
    will get picked up in the next iteration of the main scheduler loop.

    If it is a function, arguments and keyword arguments can be pre-loaded with
    *args* and *kwargs* respectively.

    :func:`schedule` is also usable as a decorator in two ways: pre-loading
    arguments (and therefore calling it inside the decorator syntax as in
    ``@schedule(args=(...))``), or using it as a simple decorator
    (``@schedule``).

.. function:: schedule_at(unixtime, target=None, args=(), kwargs={})

    Like :func:`schedule`, but will not put the scheduled greenlet into the
    runnable queue until *unixtime*.

    Because the *unixtime* argument is required, if it is used as a decorator
    then it must be invoked inside the @-decorator syntax.

.. function:: schedule_in(*seconds*, target=None, args=(), kwargs={})

    Like :func:`schedule_at`, but the scheduled greenlet will be run *seconds*
    (int or float) seconds after the :func:`schedule_in` call rather than at a
    particular unix timestamp.

.. function:: schedule_recurring(*seconds*, target=None, args=(), kwargs={})

    Schedules a function (*target* may not be a greenlet here) to be run at
    an interval of *seconds*, with *args* and *kwargs* pre-loaded.

.. function:: schedule_exception(*exception*, *target*)

    Schedules *target*, which must be a greenlet, to have *exception* raised in
    it immediately.

.. function:: schedule_exception_at(*unixtime*, *exception*, *target*)

    Schedules *target*, which must be a greenlet, to have *exception* raised in
    it at (or shortly after) *unixtime* timestamp.

.. function:: schedule_exception_in(*seconds*, *exception*, *target*)

    Schedules *target*, which must be a greenlet, to have *exception* raised in
    it after *seconds* seconds have elapsed.

.. function:: end(*target*)

    Schedules a :class:`GreenletExit <greenhouse.compat.GreenletExit>` to be
    raised in *target* (a greenlet) immediately, killing *target*.

.. function:: add_exception_handler(handler)

    *handler* should be a function accepting 3 arguments *type*, *exception*,
    *traceback* - the triple returned by ``sys.exc_info()``. Whenever there is
    an unhandled traceback in a scheduled greenlet, all exception handlers will
    be called with the relevant type/exception/traceback.

    A good one to add is in the standard library:
    ``traceback.print_exception``.
