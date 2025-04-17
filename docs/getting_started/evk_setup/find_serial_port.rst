Finding the Serial Port
-----------------------

In preparation for connecting and flashing, it is good to know the serial port of the device.

.. tabs::

   .. tab:: :fab:`windows;fa-xl` Windows

      Use Device Manager to find the port. It is listed under ``Ports (COM & LPT)`` as ``USB Serial Port`` or ``Enhanced COM Port``.
      It's most likely ``COMx`` where ``x`` is 3 or higher.

   .. tab:: :fab:`linux;fa-xl` Linux

      It's likely ``/dev/ttyUSBx`` where ``x`` is 0 or some other integer.

PySerial has a simple tool for listing all ports available::

   python -m serial.tools.list_ports
