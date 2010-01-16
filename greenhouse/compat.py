try:
    from greenlet import greenlet, GreenletExit
except ImportError, error: #pragma: no cover
    try:
        from py.magic import greenlet
        GreenletExit = greenlet.GreenletExit
    except ImportError:
        # suggest standalone greenlet, not the old py.magic.greenlet
        raise error


__all__ = ["greenlet", "main_greenlet", "GreenletExit"]

main_greenlet = greenlet.getcurrent()
