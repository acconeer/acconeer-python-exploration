Product offering
================

The Acconeer offer consists of two parts, hardware and software, as illustrated in :numref:`fig_acconeer_offer`. In addition, Acconeer also provides various tools to aid the customer in the development process.

.. _fig_acconeer_offer:
.. figure:: /_static/introduction/fig_acconeer_offer.png
    :align: center

    The Acconeer offer.

This document site is currently being upgraded with the addition of our new A121 component, so please have some patience until we have completed this.
See the :ref:`handbook` for more information on A111 vs A121.

The A111 sensor is the core of the hardware offer and is available in modules and in evaluation kits. The purpose of the evaluation kit is to provide a platform to get acquainted with the pulsed coherent radar and to start use case evaluation. The sensor evaluation kits are based on Raspberry Pi, which is a well-known and available platform which also allows you to connected other types of sensors. The module is an integration of the A111 and a microcontroller unit (MCU) and has its own evaluation kit. Just as the sensor evaluation kit it can be used to get familiar with the pulsed coherent radar technology and get started with use case development. It can also be included as a single unit in your product to decrease your development cost and decrease time to market.

:numref:`fig_system_structure` outlines the software structure, platform for running it, and communication interfaces. The software for controlling the A111 sensor and retrieving data from it is called Radar System Software (RSS) and provides output at two levels:

* Service, provides pre-processed sensor data

* Detector, provides results based on the sensor data - all Detectors are based on Services

.. _fig_system_structure:
.. figure:: /_static/introduction/fig_system_structure.png
    :align: center
    :width: 65%

    System structure, the RSS software runs on a host that controls the sensor.

RSS is provided as library files and is written in C and designed to be portable between different platforms, a list of currently supported processor architectures and toolchains are available at the `Acconeer developer site <https://developer.acconeer.com>`__. Apart from RSS, Acconeer provides Example applications and stubbed software integration source code in the Software development kits (SDKs) as well as full reference integrations for selected platforms.

Acconeer provides four types of applications:

* Example applications: Example of how to use RSS, available in SDK at Acconeer developer site

* Reference applications: Use case specific reference application available in SDK at Acconeer developer site

* Exploration server: Application streaming data from sensor evaluation kit to PC, available in SDK for Raspberry Pi at Acconeer developer site

* Module server: Application providing a register write based interface to Acconeer modules, available in Module software image at Acconeer developer site.

Both RSS and Applications run on a host platform and Acconeer provides a software integration reference with guidance on how to integrate to your host platform as well as specific integration for the modules and evaluation kits that Acconeer provides.

* For our EVK platforms we provide a software package and for

    * Raspberry Pi it includes hardware abstraction layer, device drivers, and build environment provided as source code

    * Modules it includes hardware abstraction layer and build environment provided as source code

* For STM32 platforms we provide example integration files and instructions for how to set up a project in STM32CubeIDE.

* Other ARM Cortex M0, M4 and M7 based platform can easily be used by writing a custom implementation of the HAL integration layer. A handful functions that use MCU specific driver functions for accessing timers, SPI and GPIO have to be implemented.

For more detailed information on how to implement the HAL integration layer used by RSS, there is a user guide available at `developer.acconeer.com <https://developer.acconeer.com>`__ under *Documents and learning > SW*.

Based on these deliveries it is possible for the customer to create their own integration layer for any platform that uses a supported processor architecture. The currently available products and corresponding software deliveries are listed in :numref:`fig_product_sw_offer`, refer to documentation for each specific product for further details.

.. _fig_product_sw_offer:
.. figure:: /_static/introduction/fig_product_sw_offer.png
    :align: center
    :width: 92%

    Products and software deliverables.

At `acconeer.com <https://acconeer.com>`__, there are modules and SDK variants and they all contain RSS, Software integration, and Example applications. The Module software image contains RSS, software integration, and Module server.
The module can be used in two different setups:

* Stand-alone module: The module has got no dependency on external controllers. The application is customized to a specific use case by the customer and runs on the embedded MCU. The customers application is accessing the RSS API via a software interface.

* Controlled module: The module is connected to an external controller where the customer runs their application software. The customers are accessing the RSS API via a hardware interface through the module software, that provided register mapped protocol.

The two setups listed above are also illustrated in :numref:`fig_setups`.

.. _fig_setups:
.. figure:: /_static/introduction/fig_setups.png
    :align: center
    :width: 97%

    Setup.

For the Stand-alone module setup the customer should use the RSS library and Software integration source code provided in the corresponding SDK and build their own application on these deliveries. For the Controlled module regime, i.e. the modules designed by Acconeer, the complete software that runs on the module is delivered as an image. The customer can freely select between these two options, Acconeer supports both.
