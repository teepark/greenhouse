================================================
:mod:`greenhouse.pool` -- Managed Greenlet Pools
================================================

.. module:: greenhouse.pool
.. moduleauthor:: Travis J Parker <travis.parker@gmail.com>

.. class:: OneWayPool

    OneWayPool is a pool object whose greenlets accept input, but produce no
    output. This is the most basic kind of pool.

    Instantiate it with a function and optional size integer (default 10). The
    function can take any combination of positional and/or keyword arguments.

    .. method:: start()

        Creates the greenlets used by the pool and schedules them (they will be
        blocked if the scheduler reaches them before any input is entered for
        the pool).

    .. method:: close()

        Destroys the greenlets associated with the pool object. This will be
        called by default when the pool object becomes eligible for garbage
        collection.

    .. method:: put(\*args, \*\*kwargs)

        The arguments (and keyword arguments) should match what the pool's
        function accepts. This will run the pool's function in one of the
        pool's greenlets.

    OneWayPools also support the context manager protocol, simply calling
    :meth:`start` on enter and :meth:`close` on exit.

.. class:: Pool

    This is a subclass of OneWayPool, and the documentation of OneWayPool fully
    applies here (nothing is overridden, including constructor signature).

    What is added is output from the functions run by the pool. The return
    values of the functions are retrievable via the :meth:`get` method.

    .. method:: get()

        Retrieve a result (return value) from a previous invocation of the pool
        function by one of its greenlets, and remove that result from the queue
        of retrievable results.

        If there are no un-retrieved results, this call blocks until there are.

.. class:: OrderedPool

    Because the various function invocations by the pool may complete in a
    different order than they were started, this subclass of :class:`Pool`
    guarantees that the order results are pulled via :meth:`~Pool.get` is the
    same as the order in which they were :meth:`~OneWayPool.put`.

.. function:: map(function, items, pool_size=10)

    A simple wrapper around a short-use OrderedPool, this behaves like the
    built-in ``map`` function, but it will run the function invocations in
    greenlets.
