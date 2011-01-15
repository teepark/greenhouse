from greenhouse.compat import *
from greenhouse.scheduler import *
from greenhouse.utils import *
from greenhouse.pool import *
# scheduler.state.poller needs to be in place before the io import
import greenhouse.poller
from greenhouse.io import *
from greenhouse.emulation import *
from greenhouse.backdoor import *


VERSION = (0, 6, 0, '')

__version__ = ".".join(filter(None, (str(x) for x in VERSION)))

# prime the pump. if there is a traceback before the mainloop greenlet
# has a chance to get into its 'try' block, the mainloop will die of that
# traceback and it will wind up being raised in the main greenlet
@schedule
def f():
    pass
pause()
del f
