.. _a212_pcb_guidelines:

PCB guidelines
==============

As no RF components are required for the sensor integration, low-cost FR-4 type PCBs can generally be used. The following sections provide important information how to optimize the sensor PCB layout for good far-field directivity and side lobe level.

Component placement and routing
-------------------------------

The A212 sensor integrates folded dipole antennas, with the internal IC package ground plane extending beneath the entire sensor area serving as the primary ground reference. To further enhance directivity, the antenna ground plane should be extended onto the PCB by connecting all GND pads to the top copper layer. The PCB ground plane area adjacent to the sensor acts as a reflector and should therefore be a solid copper pour with minimal routing or external components, see :numref:`fig_a212_pcb_back_side_components_3D`.


.. _fig_a212_pcb_back_side_components_3D:
.. figure:: /images/hw_images/A212_pcb_back_side_components_3D.svg
    :align: center
    :width: 75%

    A212 on PCB with E and H-planes shown.

External component placement
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The preferred way is to place all external components such as decoupling capacitors and crystal on the opposite side of the sensor as this typically results in the highest directivity and lowest side lobe level. In addition, to maximize the radiated performance, consider the following:

- Minimize the amount of routing on the sensor layer, especially close to the sensor. This can be done by routing the signals to the sensor with vias placed as close as possible to the sensor pads, see :numref:`fig_a212_pcb_back_side_components`. The ground plane area inside the footprint has lower impact on the radiated performance and therefore some vias and short traces are preferably placed there.
- Whenever the assembly process allows, remove thermal reliefs on all sensor pads.
- Choose small pad size vias such as 0.4-0.45 mm or smaller.
- Minimize copper clearance for traces, vias, and pads on the sensor layer to maximize the ground plane area close to the sensor.
- Add stitching vias with <0.6 mm spacing at the PCB outer edge to suppress potential edge radiation.

.. _fig_a212_pcb_back_side_components:
.. figure:: /images/hw_images/A212_pcb_back_side_components.svg
    :align: center
    :width: 100%

    Example PCB layout with decoupling and crystal placed on sensor back side.

Ground plane size
-----------------

As the ground plane size is increased, the directivity increases because of the larger reflector size. However, the directivity does not increase monotonically with ground plane size due to constructive and destructive interference. For PCBs smaller than 20×15 mm, the H	-plane side lobe level increases, which should be considered in applications where this is important.
