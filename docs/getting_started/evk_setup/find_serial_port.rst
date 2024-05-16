Finding the serial port
-----------------------

On Windows, use device manager to find the port which will be listed as ``USB Serial Port``. It's most likely ``COMx`` where ``x`` is 3 or higher. On Linux, it's likely ``/dev/ttyUSBx`` where ``x`` is 0 or some other integer.

PySerial has a simple tool for listing all ports available::

   python -m serial.tools.list_ports
