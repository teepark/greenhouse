try:
    from greenlet import greenlet, GreenletExit
except ImportError: #pragma: no cover
    from py.magic import greenlet
    GreenletExit = greenlet.GreenletExit


__all__ = ["greenlet", "main_greenlet", "GreenletExit"]

main_greenlet = greenlet.getcurrent()
