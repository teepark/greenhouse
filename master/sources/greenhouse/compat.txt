============================================================
:mod:`greenhouse.compat` -- Greenlet and Compatibility Hacks
============================================================

.. module:: greenhouse.compat
.. moduleauthor:: Travis J Parker <travis.parker@gmail.com>

.. data:: main_greenlet

    This module attribute should always be set to the main root greenlet.

.. function:: getcurrent()

    get the current greenlet

.. class:: GreenletExit

    The GreenletExit exception from whichever greenlet module (py.magic or the
    newer standalone greenlet package). Refer to your greenlet package's
    documentation.
