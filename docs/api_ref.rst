.. _api-ref:

API reference
=============

This page provides an auto-generated summary of Acconeer Exploration Tool's API.

.. autoclass:: acconeer.exptool.a111.Client
   :members:
   :special-members: __init__

    Examples:

    .. code-block:: python

        # Autodetects serial ports.
        from acconeer.exptool.a111 import Client

        client = Client()

    .. code-block:: python

        # A client that communicates with given host over socket
        client = Client(host="192.168.XXX.YYY")

    .. code-block:: python

        # A client that communicates with a Module Server over UART
        client = Client(protocol="module", link="uart")

    .. code-block:: python

        # A client that communicates with an Exploration Server over socket
        client = Client(protocol="exploration", link="socket", host="192.168.XXX.YYY")

.. automodule:: acconeer.exptool.a111
    :members: Link, Protocol
    :undoc-members:
