try:
    from greenlet import greenlet
    try:
        from greenlet import GreenletExit
    except ImportError, error:
        try:
            GreenletExit = greenlet.GreenletExit
        except AttributeError:
            raise error
        else:
            # pypy's greenlets don't allow weakrefs to them, this fixes that
            class greenlet(greenlet):
                pass
except ImportError, error:
    try:
        from py.magic import greenlet
        GreenletExit = greenlet.GreenletExit
    except ImportError:
        # suggest standalone greenlet, not the old py.magic.greenlet
        raise error


__all__ = ["main_greenlet", "getcurrent", "GreenletExit"]

getcurrent = greenlet.getcurrent

# it's conceivable that we might not be in the main greenlet at import time,
# so chase the parent tree until we get to it
main_greenlet = getcurrent()
while main_greenlet.parent:
    main_greenlet = main_greenlet.parent
