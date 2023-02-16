.. _handbook-physical-integration:

Physical integration
====================

The A111 sensor contains the mmWave front-end, digital control logic, digitization of received signal and memory, all in one package. To integrate it in your application it is required to have a reference frequency or XTAL (24 MHz), 1.8 V supply, and a host processor, as illustrated in :numref:`fig_host_platform`, supported platforms and reference schematics are available at `developer.acconeer.com <https://developer.acconeer.com>`__.

.. _fig_host_platform:
.. figure:: /_static/introduction/fig_host_platform.png
    :align: center
    :width: 80%

    Illustration of integration into host platform, the A111 is marked with the Acconeer logo.

In addition to the above it is also important for optimized integration to consider the electromagnetic (EM) environment, both in terms of what is placed on top of the sensor as well as to the side of the sensor. To evaluate the EM integration a Radar loop measurement can be conducted by placing an object in front of the sensor and rotating the sensor around its own axis, as illustrated in :numref:`fig_radar_loop_pattern`. The received energy from e.g. the Envelope Service can then be used to plot the amplitude versus rotation angle (:math:`\theta`).

.. _fig_radar_loop_pattern:
.. figure:: /_static/introduction/fig_radar_loop_pattern.png
    :align: center
    :width: 85%

    Setup configuration for radar loop pattern measurements.

The radiation pattern of the integrated antennas will be affected by anything that is put on top of the sensor as a cover. The transmission through a material is given by 1-:math:`\gamma`, where :math:`\gamma` is the reflectivity calculated in Equation 3. Hence, materials with low reflectivity are good materials to use as a cover on top of the sensor, plastic is a good choice and the sensor is not sensitive to the color of the material. :numref:`fig_h_plan_pattern` shows the measured Radar loop pattern for 3 different scenarios, plastic (ABS), gorilla glass (GorillaGlass) and free space (FS). To further optimize the cover integration the thickness of the material should be considered. One can also use a layered cover which uses materials of different :math:`\varepsilon` for optimum matching to the medium in which the signal is going to propagate or even to increase the directivity, as shown in :numref:`fig_h_plan_pattern`, where the beam width has been decreased by adding material on top of the sensor. More information on the EM integration aspects can be found in the “Hardware and physical integration guideline” document available at `developer.acconeer.com <https://developer.acconeer.com>`__.

.. _fig_h_plan_pattern:
.. figure:: /_static/introduction/fig_h_plan_pattern.png
    :align: center
    :width: 85%

    Integration of sensor cover and how different materials impact the radiation pattern on the H-plane. The object used is a trihedral corner of radius 5 cm.
