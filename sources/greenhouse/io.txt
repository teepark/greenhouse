================================================
:mod:`greenhouse.io` -- Cooperative I/O Drop-Ins
================================================

.. module:: greenhouse.io
.. moduleauthor:: Travis J Parker <travis.parker@gmail.com>

.. class:: Socket

    Socket is a drop-in replacement for python standard library sockets which
    will block greenlets in the same manner that standard sockets (in blocking
    mode) block threads.

    Create them with optional *family*, *type* and *proto* arguments which
    default to ``socket.AF_INET``, ``socket.SOCK_STREAM``, and
    ``socket.IPPROTO_IP`` respectively.

    .. method:: accept()

        Block until a new connection on the bound host/port is made, return a
        two-tuple of a socket connected to the client, and the client's ip
        address.

    .. method:: bind(address)

        Set the socket to operate at *address*. The format of *address* depends
        on the family type. For TCP sockets, this is a (host, port) pair.

    .. method:: close()

        Close the socket. After queued data is flushed, the remote end will not
        receive any more data. All operations attempted on this socket will
        fail from this point on.

    .. method:: connect(address)

        Establish a new connection to a remote socket at *address*. The format
        of *address* depends on the socket's address family. This call will
        block until the connection is made.

    .. method:: connect_ex(address)

        Like ``connect()``, except that if the connection cannot be immediately
        made, it returns an error code instead of blocking. A return value of 0
        indicates success.

    .. method:: dup()

        Returns a new copy of the current socket object (on the same
        descriptor).

    .. method:: fileno()

        Returns the file descriptor (an integer) for the socket.

    .. method:: getpeername()

        For a connected socket, returns the address information of the remote
        side of the connection.

    .. method:: getsockname()

        For a connected socket, returns the address information of the local
        side of the connection.

    .. method:: getsockopt(level, optname[, buflen])

        Returns the value of the given socket option. The constants used for
        arguments to this function are defined in the standard library
        ``socket`` module. See the documentation for the getsockopt method of
        socket objects in the stdlib socket module, and the unix manpage
        *getsockopt(2)*.

    .. method:: gettimeout(self):

        Returns the float of seconds before a blocking socket operation will
        raise a ``timeout`` instance (from the stdlib socket module).

    .. method:: listen(backlog)

        Listen for connections made to the socket, queueing up to *backlog*
        connections.

    .. method:: makefile([mode[, bufsize]])

        Returns a file-like object associated with the socket. The optional
        *mode* and *bufsize* arguments are interpreted the same way as other
        files.

    .. method:: recv(bufsize[, flags])

        Receives data from the socket, blocking the current greenlet if nothing
        is already available to be read. *bufsize* is the maximum amount of
        data to be read, but it may return less and that does not indicate that
        the connection is closed. See the unix manpage for *recv(2)* for the
        meaning of the *flags* argument.

    .. method:: recv_into(buffer[, bufsize[, flags]])

        Like ``recv()``, but places received data into the provided *buffer*
        instead of creating a new string. Also *bufsize* is now optional, it
        defaults to 0, which indicates to use the size of the buffer.

    .. method:: recvfrom(bufsize[, flags])

        Like ``recv()``, but returns a pair ``(string, address)`` where
        *address* is the address of the remote end of the connection.

    .. method:: recvfrom_into(buffer[, bufsize[, flags]])

        Receives data placing it directly into the *buffer* object, *bufsize*
        defaults to the buffer length, and returns a pair ``(bytes, address)``,
        the number of bytes received and placed in the buffer, and the address
        from which it was received.

    .. method:: send(data[, flags])

        Send data over the socket, which must be connected already. The
        optional *flags* argument has the same meaning as for ``recv()``.
        Returns the number of bytes actually sent, which may be less than the
        length of the provided data; applications are responsible for ensuring
        that everything gets sent.

    .. method:: sendall(data[, flags])

        Like ``send()``, but continues to send until all the provided data has
        been sent or an error occurs.

    .. method:: sendto(data[, flags], address)

        Sends data to *address*. The socket must not already be connected.

    .. method:: setblocking(flag)

        This method has been overridden to do nothing. The reason is that the
        underlying standard library socket is already set to non-blocking mode
        and otherwise-blocking methods are overridden to block only a greenlet.
        To get a socket that doesn't even block the greenlet: make sure
        greenhouse is not monkeypatched in (see
        :func:`greenhouse.emulation.socket`), create a standard-library
        socket, and set it to non-blocking mode.

    .. method:: setsockopt(level, option, value)

        Set the given socket *option* to *value*. See the unix man page
        *setsockopt(2)*. The symbolic constants for arguments are defined in
        the standard library ``socket`` module.

    .. method:: shutdown(how)

        Closes one or both ends of the connection. if *how* is ``SHUT_RD``, it
        shuts down the receiving end, ``SHUT_WR`` closes the writing end, and
        ``SHUT_RDWR`` closes both. Those 3 constants are defined in the
        standard library ``socket`` module.

    .. method:: settimeout(timeout)

        Sets the number of seconds before a ``socket.timeout`` exception is
        raised when waiting on a blocking operation. Can also be set to
        ``None`` so that it has no timeout.

.. class:: File

    The greenhouse drop-in replacement for the built-in ``file`` type (which is
    also what the built-in ``open`` function returns), this file object makes
    sure that all blocking operations block only the current greenlet.

    Create instances just like how you call ``file`` or ``open``: with the
    filename and an optional mode.

    Iterating over ``File`` instances yields the lines from the file, just like
    regular built-in files.

    .. classmethod:: fromfd(descriptor[, mode])

        Create a cooperating greenhouse file object from a pre-existing file
        descriptor.

    .. method:: close()

        Close the file object and free up the descriptor.

    .. method:: fileno()

        Returns the file descriptor integer.

    .. method:: flush()

        Has no effect in this object as it does no internal write buffering.

    .. method:: read([bytes])

        Reads up to *bytes* bytes from the file and returns the string.

    .. method:: readline()

        Reads from the file until a newline character is found, and returns the
        line string.

    .. method:: readlines()

        Reads the full file into memory and returns a list of the text split on
        newlines.

    .. method:: seek(position[, whence])

        Sends the cursor on the file descriptor to *position*, relative to a
        location dependent on *whence*. The default is ``os.SEEK_START`` for
        the beginning of the file, but other valid values for *whence* are
        ``os.SEEK_END`` and ``os.SEEK_CUR`` for the end of the file and the
        current position respectively.

    .. method:: tell()

        Returns the current position of the file descriptor's cursor relative
        to the beginning of the file.

    .. method:: write(data)

        Write the string *data* to the file.

    .. method:: writelines(sequence)

        Writes the strings in *sequence* to the file. ``writelines()`` does not
        add line separators to the *sequence* items.

.. function:: pipe()

    Creates an inter-process communication pipe, returning it as a pair of
    :class:`File` objects ``(read, write)`` for the two ends of the pipe.
