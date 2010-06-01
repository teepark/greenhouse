============================================================
:mod:`greenhouse.compat` -- Greenlet and Compatibility Hacks
============================================================

.. module:: greenhouse.compat

.. class:: greenlet

    The underlying greenlet class. Raw (user-created) greenlets can be used
    with the greenhouse scheduler. The only thing to be aware of is the raw
    greenlet's parent - the greenlet to which it switches when it dies may or
    may not in the greenhouse scheduler. To fully swallow the cool-aid and let
    greenhouse manage a greenlet created outside of greenhouse, just set the
    ``parent`` attribute of the greenlet to ``greenhouse.scheduler.mainloop``.

.. data:: main_greenlet

    This module attribute should always be set to the main greenlet.

.. class:: GreenletExit

    The GreenletExit exception from whichever greenlet module (py.magic or the
    newer standalone greenlet package). Refer to your greenlet package's
    documentation.
