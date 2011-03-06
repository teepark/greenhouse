========
Tutorial
========

.. highlight:: python


Grabbing URLs in Parallel
=========================


Since the strength of greenhouse is the ability to do I/O operations in
parallel, lets take the simple example of fetching a list of URLs with HTTP
and explore the APIs that greenhouse makes available.


Just Schedule the Coroutines
----------------------------

A greenhouse coroutine wraps a function, so since our coroutines will be
fetching urls, let's write a function that fetches a URL and places it in a
results collector.

To get the urls we can just use the simple standard library module urllib2, but
in order to make sure that it only blocks a coroutine we need to use greenhouse
to import it.

::

    import greenhouse
    urllib2 = greenhouse.patched("urllib2")

    def _get_one_url(url, results):
        page = urllib2.urlopen(url).read()
        results.append((url, page))

For the full implementation we just need to schedule a coroutine for each url
we need to grab.

::

    def get_urls(urls):
        results = []
        for url in urls:
            greenhouse.schedule(_get_one_url, args=(url, results))
        return results

So this starts *all* the I/O in parallel and returns a list into which the
results will appear as they come in.

That's nice, but we'd really like some better notification when everything is
finished. We can probably live with blocking until all the results come back as
long as we know that they are being fetched in parallel. So let's use one of
the simplest synchronization utilities available,
:class:`Event<greenhouse.utils.Event>`, and have it trigger when all the
results are in.

::

    import greenhouse
    urllib2 = greenhouse.patched("urllib2")

    def _get_one_url(url, results, count, done_event):
        page = urllib2.urlopen(url).read()
        results.append((url, page))

        if len(results) == count:
            done_event.set()

    def get_urls(urls):
        count = len(urls)
        results = []
        done = greenhouse.Event()

        for url in urls:
            greenhouse.schedule(_get_one_url, args=(url, results, count, done))

        done.wait()

        return results

That'll about do it! We schedule one coroutine for each url we need fetched and
have that coroutine get it, then block on the
:class:`event<greenhouse.utils.Event>` until the last one has come back.


Drive It Off a Queue
--------------------

The above implementation still has at least one deficiency though -- we may
want to cap the amount of parallelism in case we wind up with an especially
long list of urls, in which case each coroutine would need to fetch multiple
urls in serial. But they should all be pulling from a single list so that it is
the coroutine that comes back with its first result the fastest that fetches a
second one.

Sounds like a job for a queue. We'll use a
:class:`Queue<greenhouse.utils.Queue>` and follow the urls with a sentinel
stopper for each coro we have running.

::

    import greenhouse
    urllib2 = greenhouse.patched("urllib2")

    def _get_multiple_urls(input_queue, output_queue, stop):
        while 1:
            url = input_queue.get()
            if url is stop:
                break

            page = urllib2.urlopen(url).read()
            output_queue.put((url, page))

    def get_urls_queue(urls, parallel_cap=None):
        in_q = greenhouse.Queue()
        out_q = greenhouse.Queue()
        stop = object()
        parallel_cap = parallel_cap or len(urls)

        for i in xrange(parallel_cap):
            greenhouse.schedule(_get_multiple_urls, args=(in_q, out_q, stop))

        for url in urls:
            in_q.put(url)

        for i in xrange(parallel_cap):
            in_q.put(stop)

        for url in urls:
            yield out_q.get()

By also driving the output off of a :class:`Queue<greenhouse.utils.Queue>`, we
are able to yield the results one at a time which is another nice win.


Pool Your Coroutines
--------------------

The pattern above using an input and output queue is a fairly common one and
easy abstract away, so that's why we have :class:`Pools<greenhouse.pool.Pool>`.

::

    import greenhouse
    urllib2 = greenhouse.patched("urllib2")

    def _pool_job(url):
        return (url, urllib2.urlopen(url).read())

    def get_urls_pool(urls, parallel_cap=None):
        parallel_cap = parallel_cap or len(urls)

        with greenhouse.Pool(_pool_job, parallel_cap) as pool:
            for url in urls:
                pool.put(url)

            for url in urls:
                yield pool.get()

The :class:`Pool<greenhouse.pool.Pool>` class handles some of the mundane
things in our queue example above: having the coros loop until they get the
stopper, scheduling them, sending the stopper through. The context manager
use in this example simply calls :meth:`start()<greenhouse.pool.Pool.start>` in
the entry, and :meth:`close()<greenhouse.pool.Pool.close>` in the exit.


Order Matters
-------------

One other deficiency of every implementation so far has been that they don't
necessarily produce the results in order, which is why we have had to include
the url with its result all along. To order them we'd have to either wait until
they were all finished and then sort them, or we could keep a cache of those
results that came in out of order and re-order on the fly. Luckily there is
:class:`OrderedPool<greenhouse.pool.OrderedPool>`, which does the second
approach for us.

::

    import greenhouse
    urllib2 = greenhouse.patched("urllib2")

    def _pool_job(url):
        return urllib2.urlopen(url).read()

    def get_urls_ordered_pool(urls, parallel_cap=None):
        parallel_cap = parallel_cap or len(urls)

        with greenhouse.OrderedPool(_pool_job, parallel_cap) as pool:
            for url in urls:
                pool.put(url)

            for url in urls:
                yield pool.get()


A Further Abstraction
---------------------

:class:`OrderedPool<greenhouse.pool.OrderedPool>` is great in that it can be a
persistent object and accept jobs and return results over a long period of
time, but for our usage here we just need to crank through a list and be done
with it. :func:`greenhouse.map<greenhouse.pool.map>` is a nice abstraction of
:class:`OrderedPool<greenhouse.pool.OrderedPool>` for that purpose. It works
just like the standard python ``map`` function, except that it spreads the jobs
across an :class:`OrderedPool<greenhouse.pool.OrderedPool>` (and takes an
optional argument for the number of workers it should have)

::

    import greenhouse
    urllib2 = greenhouse.patched("urllib2")

    def get_urls_map(urls, parallel_cap=None):
        parallel_cap = parallel_cap or len(urls)

        return greenhouse.map(
            lambda url: urllib2.urlopen(url).read(),
            urls,
            pool_size=parallel_cap)
