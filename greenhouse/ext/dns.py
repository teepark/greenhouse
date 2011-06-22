from __future__ import absolute_import, with_statement

import socket

from ..emulation import patched

exception = patched("dns.exception")
rdatatype = patched("dns.rdatatype")
resolver = patched("dns.resolver")
reversename = patched("dns.reversename")

DNS_CACHE_SIZE = 512


class LRU(object):
    def __init__(self, size):
        self._keyed = {}
        self._head = None
        self.size = size

    def _set_head(self, item):
        head = self._head
        self._head = item
        if head:
            item.prev = head.prev or head
            item.prev.next = item
            item.next = head
            head.prev = item
        else:
            item.prev = item.next = None

    def _remove_item(self, item, from_keyed=True):
        if item.prev:
            item.prev.next = item.next
        if item.next:
            item.next.prev = item.prev
        if from_keyed:
            self._keyed.pop(item.key)

    def _purge(self):
        while len(self._keyed) > self.size:
            item = self._head.prev
            self._remove_item(item)

    def __contains__(self, key):
        return key in self._keyed

    def __getitem__(self, key):
        item = self._keyed[key]
        self._remove_item(item, from_keyed=False)
        self._set_head(item)
        return item.value

    def __setitem__(self, key, value):
        old_item = self._keyed.get(key, None)
        if old_item:
            self._remove_item(old_item)

        item = LRUItem(key, value)
        self._set_head(item)
        self._keyed[key] = item
        self._purge()

class LRUItem(object):
    __slots__ = ["key", "value", "next", "prev"]

    def __init__(self, key, value):
        self.key = key
        self.value = value


etc_hosts_loaded = False
etc_hosts = {}
cache = LRU(DNS_CACHE_SIZE)
resolver_obj = None

def build_resolver(filename="/etc/resolv.conf"):
    if resolver_obj is None:
        globals()['resolver_obj'] = resolver.Resolver(filename)

def load_etc_hosts(filename="/etc/hosts"):
    with open(filename) as fp:
        for line in fp:
            try:
                if (c for c in line if not c.isspace()).next() == '#':
                    continue
            except StopIteration:
                continue

            parts = line.split()
            if '::' in parts[0]:
                # not handling ipv6 yet
                continue
            for part in parts[1:]:
                etc_hosts.setdefault(part, []).append(parts[0])
    globals()['etc_hosts_loaded'] = True

def is_ipv4(name):
    try:
        socket.inet_pton(socket.AF_INET, name)
    except socket.error:
        return False
    return True

def resolve(name):
    build_resolver()

    if is_ipv4(name):
        return [name]

    if not etc_hosts_loaded:
        load_etc_hosts()

    # if it's in /etc/hosts then use that
    if name in etc_hosts:
        return etc_hosts[name][:]

    # return it out of the cache if it's there
    if name in cache:
        return cache[name][:]

    results = [x.to_text() for x in resolver_obj.query(name)]
    cache[name] = results[:]
    return results
