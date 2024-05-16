Setting up your Raspberry Pi EVK for A121
=========================================

This applies to the XE121 kit (mounted on a Raspberry Pi).

Overview
--------

At large, these are the steps you'll need to take:

* Assemble your evaluation kit
* Set up your Raspberry Pi
* Load the Acconeer Raspberry Pi SDK onto your Raspberry Pi
* Run the exploration server application on your Raspberry Pi

Setup
-----
Start a terminal window and type ``sudo raspi-config``, then:

* In Localisation Options, select the appropriate timezone.
* In Interfacing Options, enable SPI and I2C and the SSH interfaces.

Install libgpio2 by running::

   sudo apt install libgpiod2

If you use a 64-bit version of the Raspberry Pi OS, then the following must be done
to install support for 32-bit binaries::

   sudo dpkg --add-architecture armhf
   sudo apt update
   sudo apt install libc6:armhf libgpiod2:armhf

Reboot to the let the changes take effect.

Running the exploration server application
------------------------------------------

Start the exploration server application on your Raspberry Pi located under ``out`` in the SDK archive::

   $ cd path/to/the/sdk
   $ ./out/acc_exploration_server_a121

Find the IP address of your Raspberry Pi by running ``ip a`` in its terminal.
