FAQ and common issues
=====================

Python related
--------------

#) Import errors with NumPy on Linux

   The solution is to remove all duplicates of NumPy and reinstall using pip::

      sudo apt-get remove python3-numpy
      python -m pip uninstall numpy       # Repeat until no NumPy version is installed
      python -m pip install --user numpy

   Depending on your environment, you might have to replace ``python`` with ``python3`` or ``py``.
