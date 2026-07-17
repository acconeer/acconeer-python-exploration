.. _integration-a121-waveguides-and-horns:

============================
Waveguides and horn antennas
============================

A waveguide is a hollow metal pipe where wave propagation is restricted in accordance with certain field configurations or so-called modes. A horn antenna essentially consists of a waveguide with an aperture opening designed to transition guided modes into free space propagation, see :numref:`fig_horn_antenna_and_PCB_3D`. Horn antennas are highly efficient radiators with good sidelobe suppression and therefore suitable for demanding radar use cases such as tank level and industrial level sensing.

The A121 sensor can couple to a waveguide and horn antenna, thus enabling high directivity and good sidelobe suppression. The dimensions of the waveguide determine which modes are excited as well as the sensor input impedance and Tx to Rx coupling. In the following we will only consider conical horns although rectangular or other shapes can also be constructed.

.. _fig_horn_antenna_and_PCB_3D:
.. figure:: /_static/hw_images/A121_conical_horn_3D.png
    :align: center
    :width: 50%

    Example conical horn antenna (half-section shown) with mode filter.

To fit a circular waveguide around the sensor, the waveguide must have a minimum diameter including some mechanical clearance. This inherently results in an overmoded waveguide, i.e. more than one propagating mode is excited. The far-field patterns of two example horn antenna designs of lengths 25 and 40 mm are shown in :numref:`L25_horn_antenna_farfields`.

- L25 horn: 15 dB Tx+Rx gain
- L40 horn: 20 dB Tx+Rx gain

.. _L25_horn_antenna_farfields:
.. figure:: /_static/handbook/a121/horn_antenna/L25_L40_horn_antennas.svg
    :align: center
    :width: 100%

    L25 and L40 horn antenna far-fields.

Horn antenna radomes
--------------------
A radome or plastic cover can be placed after the horn antenna. The radome thickness should be chosen as described in :ref:`integration-a121-radome-thickness`.

Custom designs
--------------

Customized horn antennas and waveguides can also be constructed where the size and shape is optimized to satisfy product requirements. Acconeer provides a design service for this, see `Acconeer design services <design_services_>`_ for details.

.. _design_services: https://developer.acconeer.com/home/design-services/
