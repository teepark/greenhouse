====================================================================
:mod:`greenhouse.poller` -- A Common Interface for epoll/poll/select
====================================================================

.. module:: greenhouse.poller
.. moduleauthor:: Travis J Parker <travis.parker@gmail.com>

The poller module is mainly internal to greenhouse, but the building blocks it
provides are also generally useful.

The classes in this module all support a common interface, which is described
here on the :class:`Select` class.

.. class:: Select

    This is a poller object that uses the ``select(2)`` system call.

    The constructor takes no arguments.

    .. attribute:: INMASK

    .. attribute:: OUTMASK

    .. attribute:: ERRMASK

    .. method:: register(fd, mask=None)

        Pushes *mask* onto the registration stack for descriptor *fd*.

        *mask* should be some bitwise OR combination of the :attr:`INMASK`,
        :attr:`OUTMASK`, and :attr:`ERRMASK` class attributes. It signifies
        what kinds of events (readable, writable, error occurred respectively)
        the poller will track for the given descriptor.

    .. method:: unregister(fd)

        Pops off the top of the registration stack for descriptor *fd*.

    .. method:: poll(timeout)

        Runs the poller until *timeout* seconds or some result is ready.
        Returns a list of ``(fd, mask)`` pair where *fd* is a file descriptor
        with some sort of network readiness state, and *mask* is a bitwise OR
        combination of :attr:`INMASK`, :attr:`OUTMASK`, and :attr:`ERRMASK`
        indicating the kind of network state.

.. class:: Poll

    A poller class that supports exactly the interface of :class:`Select`, but
    uses the ``poll(2)`` system call instead of ``select(2)``. Because ``poll``
    is not available on all systems or may simply not be supported by the
    python standard library on your system, check the ``select`` module for a
    ``poll`` attribute before using this class and fall back to
    :class:`Select`.

.. class:: Epoll

    A poller class that supports the :class:`Select` and :class:`Poll`
    interface, but does it with ``epoll(7)``. This class assumes that ``epoll``
    is available and supported by the standard library, so check the ``select``
    module for an ``epoll`` attribute before using.

.. class:: KQueue

    A poller class that supports the same poller interface, but does it with
    BSD's ``kqueue(2)``. This class assumes that ``kqueue`` is available in the
    standard library ``select`` module, so check for ``select.kqueue`` before
    using.

.. function:: best

    Returns an instance of a poller class (:class:`Epoll`, :class:`KQueue`,
    :class:`Poll`, or :class:`Select` in order of preference), using the best
    poller class available based on the system and the python version.

.. function:: set(poller=None)

    Set the poller instance to be used by greenhouse's scheduler. The default
    is to create a new instance of the best kind it can, as determined by
    :func:`best`.
