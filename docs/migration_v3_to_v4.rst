Migrating from v3 to v4
=======================
Some things have changed from Exploration Tool v3.
Here are some things that may affect you when you transition to Exploration Tool v4.

(See also :ref:`changelog`, section *v4.0.0*)

General
-------
- The preferred way to install *Exploration Tool* is now via Python's package
  manager; ``pip``. Install is done with ``python -m pip install acconeer-exptool[app]``,
  which downloads and installs the *Exploration Tool App* including all its Python dependencies.

- The *Exploration Tool App* is no longer run with ``python gui/main.py``.
  The command has been replaced with ``python -m acconeer.exptool.app``,
  which can be run from anywhere.

- Standalone processing examples (earlier found under ``examples/processing``) have been moved.
  Runnable with e.g. ``python -m acconeer.exptool.a111.algo.<service or detector> --uart``

- Many modules have been moved to ``acconeer.exptool.a111``.

- The **Calibration management** section have been added to the App. This is the new way
  to handle recorded background data. Please revisit :ref:`background-data` for more information.

API changes
-----------
There have been some small API-changes for users that have extended *Exploration Tool*
by modifying or have added to the source code.

- The ``SocketClient``-, ``SPIClient``- and ``UARTClient``-classes are unified
  in a single ``Client``-class. These are the before and after:

  .. code-block:: python

        import acconeer.exptool as et

        # Before (v3)
        socket_client = et.SocketClient("192.168.XXX.YYY")

        spi_client = et.SPIClient()

        uart_client = et.UARTClient("COMX")

        # After (v4)
        socket_client = et.a111.Client(host="192.168.XXX.YYY")

        spi_client = et.a111.Client(link="spi")

        uart_client = et.a111.Client(serial_port="COMX", protocol="module")

        # Support for Exploration server over UART was added aswell:
        exploration_uart_client = et.a111.Client(serial_port="COMX", protocol="exploration")

  For more details, please see :ref:`api-ref`

- A lot of code have been moved into the ``acconeer-exptool`` -package, including
  what before was *example processing* (earlier found under ``examples/processing``).
  The old files have been moved to ``acconeer.exptool.a111.algo``
  and separated into multiple files. Here is the separation of ``sparse`` for example:

  .. code-block::

     sparse
     ├── __init__.py
     ├── __main__.py    # main function of the Algorithm module
     ├── _meta.py       # Defines the ModuleInfo, imported by the App
     ├── _processor.py  # Defines data processing
     └── ui.py          # Defines plotting

  (Please see :ref:`adding-your-own-algorithm-module` for more details)

- The way *Algorithm modules* are registered to the App have changed slightly, see
  :ref:`adding-your-own-algorithm-module`.
