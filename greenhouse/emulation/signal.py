from __future__ import absolute_import

import functools
import signal

from greenhouse import scheduler


original_signal = signal.signal

def generic_handler(delegate, *args, **kwargs):
    scheduler.schedule(delegate, args=args, kwargs=kwargs)

def green_signal(sig, action):
    original_signal(sig, functools.partial(generic_handler, action))


patchers = {
    'signal': green_signal,
}
