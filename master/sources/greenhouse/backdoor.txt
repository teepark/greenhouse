=====================================================
:mod:`greenhouse.backdoor` -- Interpreter On A Socket
=====================================================

.. module:: greenhouse.backdoor
.. moduleauthor:: Travis J Parker <travis.parker@gmail.com>


These functions enable running an additional server in greenhouse server
processes, which accepts connections and runs interactive python interpreters
over them, enabling entirely flexible and ad-hoc server administration at
runtime.

.. warning:: **backdoors are a gaping security hole**

   Make absolutely certain that you use ``"127.0.0.1"`` as the host on which
   to listen for connections, so that it will only accept connection requests
   coming from localhost. If you *must* connect to it from another machine, be
   absolutely certain that you are behind a firewall that blocks the backdoor
   port.


.. function:: run_backdoor(address, namespace=None)

   Starts a server on the specified address that creates interactive
   interpreters on any connections made.

   This function blocks; it waits for connections in the current coroutine, so
   it can be a good idea to :func:`schedule <greenhouse.scheduler.schedule>` it

   :param address: the host and port on which to listen for connections
   :type address: (string, int) tuple

   :param namespace:
        overrides the local namespace for connected interpreters. currently,
        passing a dictionary at all will cause all connected interpreters to
        share a local namespace. This means that passing an empty dict has
        different semantics than the default ``None``.
   :type namespace: dict

.. function:: backdoor_handler(sock, namespace=None)

   Starts an interactive interpreter on a connected socket.

   :param sock: the socket on which to serve the interpreter
   :type sock: :class:`greenhouse.io.Socket`

   :param namespace: the local namespace dictionary for the interpreter
   :type namespace: dict
