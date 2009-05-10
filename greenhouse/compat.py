try:
    from greenlet import greenlet
except ImportError:
    from py.magic import greenlet

main_greenlet = greenlet.getcurrent()
