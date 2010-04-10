=============
greenhouse.io
=============

.. class:: Socket([family[, type[, proto]]])

Socket is a drop-in replacement for python standard library sockets which will
block greenlets in the same manner that standard sockets block threads.

Create them with optional *family*, *type* and *proto* arguments which default
to `socket.AF_INET`, `socket.SOCK_STREAM`, and `socket.IPPROTO_IP`.

    .. method:: accept

    Block until a new connection on the bound host/port is made, return a
    two-tuple of a socket connected to the client, and the client's ip address.

    .. method:: bind(address)

    Set the socket to operate at *address*. The format of *address* depends on
    the family type. For TCP sockets, this is a (host, port) pair.

    .. method:: close()

    Close the socket. After queued data is flushed, the remote end will not
    receive any more data. All operations attempted on this socket will fail
    from this point on.

    .. method:: connect(address)

    Establish a new connection to a remote socket at *address*. The format of
    *address* depends on the socket's address family. This call will block
    until the connection is made.

    .. method:: connect_ex(address)

    Like `connect()`, except that if the connection cannot be immediately made,
    it returns an error code instead of blocking. A return value of 0 indicates
    success.

    .. method:: dup()

    Returns a new copy of the current socket object.

    .. method:: fileno()

    Returns the file descriptor (an integer) for the socket.

    .. method:: getpeername()

    For a connected socket, returns the address information of the remote side
    of the connection.

.. class:: File
