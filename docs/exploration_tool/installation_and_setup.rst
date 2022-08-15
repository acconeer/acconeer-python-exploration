Installation and setup
======================

Install
-------
Install from PyPI::

    python -m pip install --upgrade acconeer-exptool[app]

.. note::
    Depending on your environment, you might have to replace ``python`` with ``python3`` or ``py``.

The Exploration Tool application uses PySide6.
If you have other versions of PyQt/PySide installed, it may cause conflicts.
If this is the case for you, we recommend using virtual environments to separate the two installations.

To install on OS:s not supporting PySide6, install only the algo package::

    python -m pip install --upgrade acconeer-exptool[algo]

.. attention::
   You will not be able to run the Exploration Tool Application when installing only the algo package

To install the latest version from source; download or clone the repository.
Run the following command in the newly created directory::

    python -m pip install --upgrade .[app]

.. note::
   Any edit to the source code requires reinstalling ``acconeer-exptool`` unless you are using an editable install::

     python -m pip install -e .[app]

Windows Setup
-------------

Windows users might need to install drivers that allow proper function of
Acconeer's modules.

See the corresponding setup guide for your module:

- :doc:`/exploration_tool/evk_setup/xm112`
- :doc:`/exploration_tool/evk_setup/xm122`
- :doc:`/exploration_tool/evk_setup/xm132`
- :doc:`/exploration_tool/evk_setup/xc120_xe121`

Linux setup
-----------

Serial port permissions
"""""""""""""""""""""""

If you are running Linux together with an XM112, XM122, or XM132 module through UART, you probably need permission to access the serial port. Access is obtained by adding yourself to the ``dialout`` group::

    sudo usermod -a -G dialout $USER

Reboot for the changes to take effect.

.. note::
   If you have ``ModemManager`` installed and running it might try to connect to the module, which has proven to cause problems. If you are having issues, try disabling the ``ModemManager`` service.

SPI permissions
"""""""""""""""

If you are using Linux together with an XM112, you probably need permission to access the SPI bridge USB device. Either run the scripts with ``sudo`` or create an `udev` rule as follows. Create and edit::

    sudo nano /etc/udev/rules.d/50-ft4222.rules

with the following content::

    SUBSYSTEM=="usb", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="601c", MODE:="0666"

This method is confirmed to work for ***Ubuntu 20.04**.

Ubuntu 20.04
""""""""""""

To run the application on Ubuntu 20.04, ``libxcb-xinerama0-dev`` needs to be installed::

    sudo apt update
    sudo apt install -y libxcb-xinerama0-dev
