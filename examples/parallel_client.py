'''a bunch of examples of how to get a list of urls in parallel

each of them uses a different greenhouse api to retrieve a list of urls in
parallel and return a dictionary mapping urls to response bodies
'''

import urllib2

import greenhouse

# urllib2 obviously doesn't explicitly use greenhouse sockets, but we can
# override socket.socket so it uses them anyway
greenhouse.io.monkeypatch()


#
# simply schedule greenlets and use an event to signal the all clear
#

def _get_one(url, results, count, done_event):
    results[url] = urllib2.urlopen(url).read()
    if (len(results)) == count:
        done_event.set() # wake up the original greenlet

def get_urls(urls):
    count = len(urls)
    results = {}
    alldone = greenhouse.Event()

    # each url gets its own greenlet to fetch it
    for index, url in enumerate(urls):
        greenhouse.schedule(_get_one, args=(url, results, count, alldone))

    alldone.wait()
    return results


#
# create two Queue objects, one for sending urls to be processed, another for
# sending back the results.
#
# this is a little awkward for this specific use case, but is more like how you
# might do it if you don't have a bounded set of inputs but will want to
# constantly send off jobs to be run.
#

def _queue_runner(in_q, out_q, stop):
    while 1:
        url = in_q.get()
        if url is stop:
            break
        out_q.put((url, urllib2.urlopen(url).read()))

def get_urls_queue(urls, parallelism=None):
    in_q = greenhouse.Queue()
    out_q = greenhouse.Queue()
    results = {}
    stop = object()
    parallelism = parallelism or len(urls)

    for i in xrange(parallelism):
        greenhouse.schedule(_queue_runner, args=(in_q, out_q, stop))

    for url in urls:
        in_q.put(url)

    for url in urls:
        url, result = out_q.get()
        results[url] = result

    for i in xrange(parallelism):
        in_q.put(stop)

    return results


#
# the Queue example above is basically a small reimplementation of Pools
#

def _pool_job(url):
    return url, urllib2.urlopen(url).read()

def get_urls_pool(urls, parallelism=None):
    pool = greenhouse.Pool(_pool_job, parallelism or len(urls))
    pool.start()
    results = {}

    for url in urls:
        pool.put(url)

    for url in urls:
        url, result = pool.get()
        results[url] = result

    pool.close()

    return results


#
# this one returns a list of the results in an order corresponding to the
# arguments instead of a dictionary mapping them (to show off OrderedPool)
#

def _ordered_pool_job(url):
    return urllib2.urlopen(url).read()

def get_urls_ordered_pool(urls, parallelism=None):
    pool = greenhouse.OrderedPool(_ordered_pool_job, parallelism or len(urls))
    pool.start()

    for url in urls:
        pool.put(url)

    # OrderedPool caches out-of-order results and produces
    # them corresponding to the order in which they were put()
    results = [pool.get() for url in urls]

    pool.close()

    return results


#
# one last version, showcasing a further abstraction of OrderedPool
#

def get_urls_ordered_map(urls, parallelism=None):
    return greenhouse.pool.map(
            lambda u: urllib2.urlopen(u).read(),
            urls,
            pool_size=parallelism or len(urls))
