import os
import sys
try:
    from greenlet import greenlet, GreenletExit
except ImportError, error: #pragma: no cover
    try:
        from py.magic import greenlet
        GreenletExit = greenlet.GreenletExit
    except ImportError:
        # suggest standalone greenlet, not the old py.magic.greenlet
        raise error


__all__ = ["greenlet", "main_greenlet", "GreenletExit", "mkfile"]

main_greenlet = greenlet.getcurrent()

# for whatever reason, os.mknod isn't working on FreeBSD 8 (at least)
if sys.platform.lower().startswith("freebsd"):
    def mkfile(path):
        os.system("touch " + path)
else:
    def mkfile(path):
        os.mknod(path, 0644)
