################
Integrating A121
################

There are several parts that need to be considered when integrating the A121 sensor.

********************
Physical Integration
********************

Electrical
==========

The A121 sensor contains the mmWave front-end, digital control logic, digitization of received signal and memory, all in one package.
To integrate it in your application it is required to have a reference frequency or XTAL (24 MHz), 1.8 V supply, and a host processor, as illustrated in :numref:`fig_host_platform`.

.. _fig_host_platform:
.. figure:: /_static/introduction/fig_host_platform.png
    :align: center
    :width: 80%

    Illustration of integration into host platform, the A121 is marked with the Acconeer logo.

For more information, see:

* :octicon:`download` `A121 Datasheet <a121_datasheet_>`_
* :octicon:`download` `Hardware integration guideline <a121_hw_integration_guideline_>`_, in section *Electrical integration*

Electromagnetic
===============

In addition to the electrical integration, the electromagnetic environment is also important for optimized integration.

For more information, see:

* :octicon:`download` `A121 Datasheet <a121_datasheet_>`_
* :octicon:`download` `Hardware integration guideline <a121_hw_integration_guideline_>`_, in section *Electromagnetic Integration*

Lenses
======

Lenses can be used to shape the radiation pattern to fit your use case.

For more information, see:

* :octicon:`download` `Hardware integration guideline <a121_hw_integration_guideline_>`_, in section *Dielectric lenses*
* :octicon:`download` `A121 Lenses Getting Started Guide <a121_lense_guide_>`_

**************
SW Integration
**************

The A121 sensor needs to be connected to a host MCU.
In order to communicate with the sensor from the host MCU, the Acconeer RSS library is needed.
SDK packages, including the Acconeer RSS library, can be downloaded `here <sw_download_page_>`_.

Instructions on how to integrate the Acconeer RSS library can be found in the :octicon:`download` `A121 SW Integration User Guide <a121_sw_integration_guide_>`_.

.. _a121_datasheet: https://developer.acconeer.com/download/A121-datasheet
.. _a121_hw_integration_guideline: https://developer.acconeer.com/download/Hardware-integration-guideline
.. _a121_lense_guide: https://developer.acconeer.com/download/Getting-Started-Guide-A121-Lenses
.. _a121_sw_integration_guide: https://developer.acconeer.com/download/A121-SW-Integration-User-Guide-5
.. _sw_download_page: https://developer.acconeer.com/home/a121-docs-software
