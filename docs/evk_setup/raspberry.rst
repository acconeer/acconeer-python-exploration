.. _setup_raspberry:

Setting up your Raspberry Pi EVK
================================

This applies to the XC111+XR111 or XC112+XR112 kits (mounted on a Raspberry Pi).

Overview
--------

At large, these are the steps you'll need to take:

* Assemble your evaluation kit
* Set up your Raspberry Pi
* Load the Acconeer Raspberry Pi SDK onto your Raspberry Pi
* Run the streaming server application on your Raspberry Pi

For a single sensor setup, we recommend plugging the sensor into port 1 for simplicity's sake.

Setup
-----

In a terminal, run::

   sudo raspi-config

Then, under *Interfacing Options*, enable SPI and I2C.

SDK v2.8.0 or newer requires ``libgpio2``. To install::

   sudo apt update
   sudo apt install libgpiod2

If you use the XC112 board with kernel v5.4 or newer, then the following line must
be added to ``/boot/config.txt``::

   dtoverlay=spi0-1cs,cs0_pin=8

This can be done by e.g.::

   sudo sh -c 'echo "dtoverlay=spi0-1cs,cs0_pin=8" >> /boot/config.txt'

Reboot to the let the changes take effect.

Running the streaming server application
----------------------------------------

For the XC112+XR112 kit, start the streaming server application on your Raspberry Pi located under ``utils`` in the SDK archive::

   $ cd path/to/the/sdk
   $ ./utils/acc_streaming_server_rpi_xc112_r2b_xr112_r2b_a111_r2c

If you have an XC111+XR111 kit, the streaming server will instead be named ``acc_streaming_server_rpi_xc111_r4a_xr111-3_r1c_a111_r2c``.

Find the IP address of your Raspberry Pi by running ``ip a`` in its terminal.
