try:
    from greenlet import greenlet
except ImportError: #pragma: no cover
    from py.magic import greenlet


__all__ = ["greenlet"]

main_greenlet = greenlet.getcurrent()
