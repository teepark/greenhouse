from __future__ import absolute_import, with_statement

import functools
import socket

DNS_CACHE_SIZE = 512


class LRU(object):
    def __init__(self, size):
        self._keyed = {}
        self._head = None
        self.size = size

    def _set_item_head(self, item):
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

    def __setitem__(self, key, value):
        old_item = self._keyed.get(key, None)
        if old_item:
            self._remove_item(old_item)

        item = LRUItem(key, value)
        self._set_item_head(item)
        self._keyed[key] = item
        self._purge()

    def __getitem__(self, key):
        item = self._keyed[key]
        self._remove_item(item, from_keyed=False)
        self._set_item_head(item)
        return item.value

    def get(self, key, default=None):
        if key not in self._keyed:
            return default
        return self[key]

    def __delitem__(self, key):
        item = self._keyed.get(item)

        if item is None:
            raise KeyError(key)

        self._remove_item(item)

    def __repr__(self):
        if not self._keyed:
            return "<>"

        return "<%s>" % ", ".join(str(key) for key in self.iterkeys())

    def iterkeys(self):
        return (key for key, value in self.iteritems())

    def itervalues(self):
        return (value for key, value in self.iteritems())

    def iteritems(self):
        memo, item = set(), self._head
        if item is None:
            return

        while item not in memo:
            memo.add(item)
            yield (item.key, item.value)
            item = item.next

    def keys(self):
        return list(self.iterkeys())

    def values(self):
        return list(self.itervalues())

    def items(self):
        return list(self.iteritems())


class LRUItem(object):
    __slots__ = ["key", "value", "next", "prev"]

    def __init__(self, key, value):
        self.key = key
        self.value = value


etc_hosts_loaded = False
etc_hosts = {}
cache = LRU(DNS_CACHE_SIZE)
resolver = None

def build_resolver(filename="/etc/resolv.conf"):
    if resolver is None:
        globals()['resolver'] = dns_resolver.Resolver(filename)

def load_etc_hosts(filename="/etc/hosts"):
    with open(filename) as fp:
        for line in fp:
            try:
                if (c for c in line if not c.isspace()).next() == '#':
                    continue
            except StopIteration:
                continue

            parts = line.split()
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

    results = [x.to_text() for x in resolver.query(name)]
    cache[name] = results[:]
    return results

@functools.wraps(socket.getaddrinfo)
def getaddrinfo(host, port, family=0, socktype=0, proto=0, flags=0):
    socktype = socktype or socket.SOCK_STREAM
    addrs = resolve(host)
    return [(socket.AF_INET, socktype, proto, '', (addr, port))
            for addr in addrs]

@functools.wraps(socket.gethostbyname)
def gethostbyname(hostname):
    return resolve(hostname)[0]

@functools.wraps(socket.gethostbyname_ex)
def gethostbyname_ex(hostname):
    results = resolve(hostname)
    try:
        canon = resolver.query(hostname, dns_rdatatype.CNAME)
        aliases = [hostname]
    except dns.exceptions.NoAnswer:
        canon = hostname
        aliases = []

    return canon, aliases, results

@functools.wraps(socket.getnameinfo)
def getnameinfo(address, flags):
    build_resolver()
    try:
        host, port = address
    except (ValueError, TypeError):
        if not isinstance(address, tuple):
            del address
            raise TypeError('getnameinfo() argument must be a tuple')
        else:
            raise socket.gaierror(
                    socket.EAI_NONAME, "Name or service not known")

    if (flags & socket.NI_NAMEREQD) and (flags & socket.NI_NUMERICHOST):
        raise socket.gaierror(
                socket.EAI_NONAME, "Name or service not known")

    if is_ipv4(host):
        try:
            name = dns_reversename.from_address(host)

            results = resolver.query(name, dns_rdatatype.PTR)
            if len(results) > 1:
                raise socket.error(
                        "sockaddr resolved to multiple addresses")

            host = results[0].target.to_text(omit_final_dot=True)

        except dns_exception.Timeout, exc:
            if flags & socket.NI_NAMEREQD:
                raise socket.gaierror(socket.EAI_AGAIN, 'Lookup timed out')

        except dns_exception.DNSException, exc:
            if flags & socket.NI_NAMEREQD:
                raise socket.gaierror(
                        socket.EAI_NONAME, "Name or service not known")

    else:
        try:
            ips = resolve(host)
            if len(ips) > 1:
                raise socket.error('sockaddr resolved to multiple addresses')

            if flags & socket.NI_NUMERICHOST:
                host = ips[0].to_text()

        except dns_exception.Timeout, exc:
            if flags & socket.NI_NAMEREQD:
                raise socket.gaierror(socket.EAI_AGAIN, 'Lookup timed out')

        except dns_exception.DNSException, exc:
            if flags & socket.NI_NAMEREQD:
                raise socket.gaierror(
                        socket.EAI_NONAME, "Name or service not known")

    if flags & socket.NI_NUMERICSERV:
        port = str(port)
    else:
        port = socket.getservbyport(
                port, (flags & socket.NI_DGRAM) and 'udp' or 'tcp')

    return host, port


socket_patchers = {
    'getaddrinfo': getaddrinfo,
    'gethostbyname': gethostbyname,
    'gethostbyname_ex': gethostbyname_ex,
    'getnameinfo': getnameinfo,
}
