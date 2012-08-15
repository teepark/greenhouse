from __future__ import absolute_import

import ssl
import _ssl

from ..io import sockets as gsock, ssl as gssl


def wrap_socket(sock, keyfile=None, certfile=None, server_side=False,
        cert_reqs=ssl.CERT_NONE, ssl_version=ssl.PROTOCOL_SSLv23,
        ca_certs=None, do_handshake_on_connect=True, suppress_ragged_eofs=True,
        ciphers=None):
    return gssl.SSLSocket(sock, keyfile, certfile, server_side, cert_reqs,
            ssl_version, ca_certs, do_handshake_on_connect,
            suppress_ragged_eofs, ciphers)

def get_server_certificate(
        addr, ssl_version=ssl.PROTOCOL_SSLv3, ca_certs=None):
    if (ca_certs is not None):
        cert_reqs = CERT_REQUIRED
    else:
        cert_reqs = CERT_NONE
    s = wrap_socket(gsock.Socket(), ssl_version=ssl_version,
                    cert_reqs=cert_reqs, ca_certs=ca_certs)
    s.connect(addr)
    dercert = s.getpeercert(True)
    s.close()
    return ssl.DER_cert_to_PEM_cert(dercert)


patchers = {
    'wrap_socket': wrap_socket,
    'get_server_certificate': get_server_certificate,
    'sslwrap_simple': wrap_socket,
    'SSLSocket': gssl.SSLSocket,
}
