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
* Run the exploration server application on your Raspberry Pi

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

Running the exploration server application
------------------------------------------

Start the exploration server application on your Raspberry Pi located under ``out`` in the SDK archive::

   $ cd path/to/the/sdk
   $ ./out/acc_exploration_server_a111

Find the IP address of your Raspberry Pi by running ``ip a`` in its terminal.
