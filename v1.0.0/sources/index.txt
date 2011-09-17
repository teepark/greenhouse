.. greenhouse documentation master file, created by
   sphinx-quickstart on Wed Jan  6 21:46:30 2010.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

========================================
Welcome to the Greenhouse Documentation!
========================================

Greenhouse is a library that makes massively parallel I/O efficient for python,
while supporting a synchronous coding style. It requires `greenlet`_, which
provides coroutines for python as a C extension.

Using coroutines in conjunction with non-blocking I/O, greenhouse's concurrency
approach has most of the benefits of all other approaches for python, with
relatively few of their deficiencies.

Let's look at a few.

**single thread, blocking I/O**
    No parallelism whatsoever, this approach spends an inordinate amount of
    time doing nothing but waiting for network activity.

**multiple threads, blocking I/O**
    `Threads suck`_. They are too big in RAM meaning we run out of memory
    before reaching our potential in concurrent connections, we have hard to
    debug race conditions due to the unholy union of shared memory and
    preemptive scheduling, we have slow switching, and in most dynamic
    languages including python we have a GIL. `Threads are out`_.

**multiple processes, blocking I/O**
    By using processes instead of threads, a major class of race conditions is
    avoided by trading in shared memory for message passing IPC which is less
    convenient than shared memory but much less error-prone. This approach for
    python can also utilize multiple CPU cores. However, processes are larger
    even than threads, so the parallelism achievable is very limited.

**single thread, non-blocking I/O**
    Switching to non-blocking I/O allows for multiple connections in a single
    thread and process, meaning the sky is the limit for concurrency without
    high memory use. However not having I/O functions block makes control flow
    tricky. The whole procedural programming paradigm is built on executing
    tasks one at a time in order, but here we have concurrency without separate
    threads of control resulting in a hard to manage jungle of callbacks and
    "deferred" or "promise" types.

Greenhouse takes the parallelism/memory ratio strength of non-blocking I/O and
uses coroutines to provide an api that blocks from a control-flow standpoint,
but which is actually executing in a single thread and single process.

Greenlet's coroutines are much lighter in memory than operating system threads,
allowing greenlet-per-connection into the thousands, much faster to switch
between, and very importantly they **only switch cooperatively**.

Cooperative switching removes the vast majority of locking needs, reducing
overhead further beyond just the lighter threads and faster switching. It also
allows for the convenience of shared memory without the race conditions.

The emulation of the behavior of python's default blocking I/O is so good that
by monkey-patching in greenhouse's drop-in replacements for sockets and files,
most third-party libraries written to block threads will work unmodified,
blocking greenlets instead.

Index
=====

.. toctree::
    :maxdepth: 1

    tutorial/parallel-urls

    greenhouse/scheduler
    greenhouse/io
    greenhouse/utils
    greenhouse/pool
    greenhouse/compat
    greenhouse/emulation
    greenhouse/backdoor

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

.. _greenlet: http://bitbucket.org/ambroff/greenlet
.. _`Threads suck`: http://weblogs.mozillazine.org/roadmap/archives/2007/02/threads_suck.html
.. _`Threads are out`: http://tomayko.com/writings/unicorn-is-unix#threads-are-out
