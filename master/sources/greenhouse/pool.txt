================================================
:mod:`greenhouse.pool` -- Managed Greenlet Pools
================================================

.. module:: greenhouse.pool
.. moduleauthor:: Travis J Parker <travis.parker@gmail.com>

.. autoclass:: greenhouse.pool.OneWayPool
    :members:

.. autoclass:: greenhouse.pool.Pool
    :members: start, close, closing, closed, put, join, get
    :show-inheritance:

.. autoclass:: greenhouse.pool.OrderedPool
    :members: start, close, closing, closed, put, join, get
    :show-inheritance:

.. autofunction:: greenhouse.pool.map

.. autoclass:: greenhouse.pool.PoolClosed
    :show-inheritance:
