import os
import sys
try:
    from greenlet import greenlet, GreenletExit
except ImportError, error:
    try:
        from py.magic import greenlet
        GreenletExit = greenlet.GreenletExit
    except ImportError:
        # suggest standalone greenlet, not the old py.magic.greenlet
        raise error


__all__ = ["greenlet", "main_greenlet", "GreenletExit"]

# it's conceivable that we might not be in the main greenlet at import time,
# so chase the parent tree until we get to it
def _find_main():
    glet = greenlet.getcurrent()
    while glet.parent:
        glet = glet.parent
    return glet
main_greenlet = _find_main()

# for whatever reason, os.mknod isn't working on FreeBSD 8 (at least)
if sys.platform.lower().startswith("freebsd"):
    def mkfile(path):
        os.system("touch " + path)
else:
    def mkfile(path):
        os.mknod(path, 0644)
