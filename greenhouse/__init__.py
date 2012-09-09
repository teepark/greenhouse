from __future__ import absolute_import

import logging
import sys

from greenhouse.compat import *
from greenhouse.scheduler import *
from greenhouse.util import *
from greenhouse.pool import *

from greenhouse.io import *
from greenhouse.backdoor import *
from greenhouse.emulation import *


VERSION = (2, 1, 0, '')

__version__ = ".".join(filter(None, (str(x) for x in VERSION)))

# prime the pump. if there is a traceback before the mainloop greenlet
# has a chance to get into its 'try' block, the mainloop will die of that
# traceback and it will wind up being raised in the main greenlet
reset_poller()
@schedule
def f():
    pass
pause()
del f


def configure_logging(filename=None, filemode=None, fmt=None,
        level=logging.INFO, stream=None, handler=None):
    if handler is None:
        if filename is None:
            handler = logging.StreamHandler(stream or sys.stderr)
        else:
            handler = logging.FileHandler(filename, filemode or 'a')

    if fmt is None:
        fmt = "[%(asctime)s] %(name)s/%(levelname)s | %(message)s"
    handler.setFormatter(logging.Formatter(fmt))

    log = logging.getLogger("greenhouse")
    log.setLevel(level)
    log.addHandler(handler)
