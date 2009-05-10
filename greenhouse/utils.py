from __future__ import with_statement

import threading

from greenhouse import globals
from greenhouse.compat import greenlet
from greenhouse import mainloop


class Event(object):
    _guidlock = threading.Lock()
    _guid = 1

    def __init__(self):
        with self._guidlock:
            self.id = self._guid
            self.__class__._guid += 1

    def wait(self):
        globals.events['paused'][self.id].append(greenlet.getcurrent())
        mainloop.go_to_next()

    def trigger(self):
        globals.events['awoken'].update(globals.events['paused'][self.id])
        del globals.events['paused'][self.id]


class Lock(object):
    def __init__(self):
        self._locked = False
        self._ev = Event()

    def locked(self):
        return self._locked

    def acquire(self):
        while self._locked:
            self._ev.wait()
        self._locked = True

    def release(self):
        self._locked = False
        self._ev.trigger()

    def __enter__(self):
        return self.acquire()

    def __exit__(self, type, value, traceback):
        return self.release()
