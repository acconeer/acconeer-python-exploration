.. _setup_rpi_xe121:

Setting Up Your Raspberry Pi + XE121
====================================

One way to evaluate the A121 sensor is to connect a Raspberry Pi to the XE121 evaluation board.
One advantage of this setup is that the Raspberry Pi is a fairly easy environment to do C development in.
But the setup can also be used together with Exploration Tool.

.. _rpi_xe121-hw-overview:

Hardware Overview
-----------------

The image below depicts the XE121 from the front (left) and back (right).

.. figure:: /_static/hw_images/xe121_hw_overview.png
   :align: center
   :width: 80%

The image below depicts a Raspberry Pi connected to the XE121.

.. figure:: /_static/hw_images/rpi_xe121_hw_overview.jpg
   :align: center
   :width: 80%

Raspberry Pi Setup
------------------

How to setup a new Raspberry Pi can be found here: `Raspberry Pi Getting Started <https://www.raspberrypi.com/documentation/computers/getting-started.html>`_.

Additional setup needed:

Start a terminal window and type ``sudo raspi-config``, then:

* In Interfacing Options, enable SPI and I2C and the SSH interfaces.

Install ``libgpio2`` by running::

   sudo apt install libgpiod2

If you use a 64-bit version of the Raspberry Pi OS, then the following must be done
to install support for 32-bit binaries::

   sudo dpkg --add-architecture armhf
   sudo apt update
   sudo apt install libc6:armhf libgpiod2:armhf

Reboot to the let the changes take effect.

Running the Exploration Server Application
------------------------------------------

Setting up your Raspberry Pi to run the Exploration Server Application allows you to wirelessly stream data
from the Raspberry Pi to Exploration Tool on your PC via Socket.

Start by downloading the latest SDK package for Raspberry Pi from our `developer page <https://developer.acconeer.com/>`_.
The correct package is located under XE121.

Transfer the package to the Raspberry Pi.

Start the Exploration Server application on your Raspberry Pi located under ``out`` in the SDK archive::

   $ cd path/to/the/sdk
   $ ./out/acc_exploration_server_a121

Find the IP address of your Raspberry Pi by running ``ip a`` in its terminal.

Alternative Setup For Evaluation in C
-------------------------------------

The XE121 has an Arduino UNO connector, as can be seen in :ref:`rpi_xe121-hw-overview`.
This makes it easy to connect to an STM32 Nucleo development board.
Note that this is for embedded C evaluation only, Exploration Tool is not supported for this setup.

.. figure:: /_static/hw_images/nucleo_xe121_assembled.jpg
   :align: center
   :width: 80%
