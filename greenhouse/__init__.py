from __future__ import absolute_import

from .compat import *
from .scheduler import *
from .utils import *
from .pool import *

# scheduler.state.poller needs to be in place before the io import
from . import poller
poller.set()

from .io import *
from .emulation import *
from .backdoor import *


VERSION = (1, 0, 0, 'dev')

__version__ = ".".join(filter(None, (str(x) for x in VERSION)))

# prime the pump. if there is a traceback before the mainloop greenlet
# has a chance to get into its 'try' block, the mainloop will die of that
# traceback and it will wind up being raised in the main greenlet
@schedule
def f():
    pass
pause()
del f
