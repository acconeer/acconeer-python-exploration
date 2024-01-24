Common Issues
=============

Python related
--------------

#) Import errors with NumPy on Linux

   The solution is to remove all duplicates of NumPy and reinstall using pip::

      sudo apt remove python3-numpy
      python -m pip uninstall numpy       # Repeat until no NumPy version is installed
      python -m pip install --user numpy

   Depending on your environment, you might have to replace ``python`` with ``python3`` or ``py``.

#) The GUI does not load properly after updating

   Try running ``python -m acconeer.exptool.app --purge-config`` from anywhere. Accept the
   removal of the files and try starting Exploration Tool again.

   If the above does not work, please open an issue on GitHub.

#) The GUI does not start and shows an error: ``qt.qpa.plugin: Could not find the Qt platform plugin "windows" in ""``.

   This error have been witnessed when Exploration Tool is installed in an Anaconda environment.
   The error may also occur when there are non-ASCII characters in the path.

#) Dropdown menu is out of position

   This is a known issue on for Qt when running Wayland display server. The issue is fixed for Qt verison >= 6.4.0.
   (See related issue: https://bugreports.qt.io/browse/QTBUG-85297)

#) ``malloc_consolidate(): unaligned fastbin chunk detected`` appears in the console when running ET

   This error has been witnessed when running ET on Ubuntu 22.04.
   The error is usually resolved by selecting *Ubuntu on Xorg* instead of *Ubuntu* in the Ubuntu login screen
   (by pressing the cogwheel in the lower right).

#) Issues with nox tests for Python 3.12

   When running nox tests for Python 3.12, the error "AttributeError: module ‘pkgutil’ has no attribute ‘ImpImporter’. Did you mean: ‘zipimporter’?" might occur.
   To fix this run ``python -m virtualenv --upgrade-embed-wheels`` to upgrade virtualenv's packages.

Sensor related
--------------

#) What does "Experimental" mean?

   In our code you might encounter features tagged “experimental”. This means that the feature in question is an early version that has a limited test scope, and the API and/or functionality might change in upcoming releases. The intention is to let users try these features out and we appreciate feedback.
