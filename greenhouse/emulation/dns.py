from __future__ import absolute_import, with_statement

import functools
import socket

from ..ext import dns


@functools.wraps(socket.getaddrinfo)
def getaddrinfo(host, port, family=0, socktype=0, proto=0, flags=0):
    socktype = socktype or socket.SOCK_STREAM
    addrs = dns.resolve(host)
    return [(socket.AF_INET, socktype, proto, '', (addr, port))
            for addr in addrs]

@functools.wraps(socket.gethostbyname)
def gethostbyname(hostname):
    return dns.resolve(hostname)[0]

@functools.wraps(socket.gethostbyname_ex)
def gethostbyname_ex(hostname):
    dns.build_resolver()
    results = dns.resolve(hostname)
    try:
        canon = dns.resolver_obj.query(hostname, dns.rdatatype.CNAME)
        aliases = [hostname]
    except dns.resolver.NoAnswer:
        canon = hostname
        aliases = []

    return canon, aliases, results

@functools.wraps(socket.getnameinfo)
def getnameinfo(address, flags):
    dns.build_resolver()
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

    if dns.is_ipv4(host):
        try:
            name = dns.reversename.from_address(host)

            results = dns.resolver_obj.query(name, dns.rdatatype.PTR)
            if len(results) > 1:
                raise socket.error(
                        "sockaddr resolved to multiple addresses")

            host = results[0].target.to_text(omit_final_dot=True)
        except dns.exception.Timeout, exc:
            if flags & socket.NI_NAMEREQD:
                raise socket.gaierror(socket.EAI_AGAIN, 'Lookup timed out')
        except dns.resolver.NXDOMAIN:
            return (host, str(port))
        except dns.exception.DNSException, exc:
            if flags & socket.NI_NAMEREQD:
                raise socket.gaierror(
                        socket.EAI_NONAME, "Name or service not known")

    else:
        try:
            ips = dns.resolve(host)

            if len(ips) > 1:
                raise socket.error('sockaddr resolved to multiple addresses')

            if flags & socket.NI_NUMERICHOST:
                host = ips[0].to_text()
        except dns.exception.Timeout, exc:
            if flags & socket.NI_NAMEREQD:
                raise socket.gaierror(socket.EAI_AGAIN, 'Lookup timed out')
        except dns.exception.DNSException, exc:
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
