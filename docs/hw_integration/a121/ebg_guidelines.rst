.. _a121_ebg_guidelines:

============================================================
Electromagnetic bandgap structures for side lobe suppression
============================================================

The radiation pattern can be degraded by sidelobes, which represent unintentional sensitivity to directions outside the main beam. In fact, a reflection from a sidelobe direction can produce a stronger radar response than from a target in the main lobe direction. Applications where this typically happens are level sensing in tanks and silos and cargo container measurements where sidewall corners close to the radar with low path loss can produce a strong response in comparison to the target object.

The sidelobe level can be significantly improved with the use of horn antennas or reflectors. However, an alternative cost-effective way to improve the sidelobe level is by implementing Electromagnetic bandgap (EBG) structures. EBGs are periodic structures that can be implemented on the PCB top layer close to the sensor. This is shown in :numref:`fig_A121_with_ebgs_lens_and_casing`, where square patch mushroom type EBGs have been added to the PCB.

.. _fig_A121_with_ebgs_lens_and_casing:
.. figure:: /_static/hw_images/A121_ebg_pcb_lens_and_casing_3D.png
    :align: center
    :width: 75%

    A1 radar sensor with EBGs, dielectric lens and casing.

Side lobe suppression
=====================

:numref:`fig_XS121-20_EBG_eplane_3D` and :numref:`fig_XS121-20_EBG_ehplane_3D` shows two example EBG array variants. The first variant has EBGs distributed in the E-plane only (:numref:`fig_XS121-20_EBG_eplane_3D`) whereas second variant have EBG cells covering both E and H-planes.

.. list-table::
   :widths: 50 50

   * - .. figure:: /_static/hw_images/XS121_20_EBG_06_03_19x15x7x15_3D.png
          :name: fig_XS121-20_EBG_eplane_3D

          E-plane EBG example.

     - .. figure:: /_static/hw_images/XS121_20_EBG_06_03_19x19x7x7_3D.png
          :name: fig_XS121-20_EBG_ehplane_3D

          E and H-plane EBG example.

:numref:`fig_XS121_ebg_farfields` shows Tx+Rx far-field measurements with and without EBGs for two EBG variants. Both variants improve the E-plane side lobe level by approximately 10 dB at +/-90 deg angles. We also notice a small increase in boresight gain as the EBG reflection phase have been optimized. The E and H-plane EBG implementation yields some further SLL improvement with the cost of additional PCB routing complexity.

.. _fig_XS121_ebg_farfields:
.. figure:: /_static/hw_images/XS121-20-EBG_v1.1.svg
    :align: center
    :width: 100%

    Normalized far-fields with and without EBGs.

Impact of product enclosure
===========================

Increased side lobes can occur from spillover radiation hitting the product enclosure walls, PCB standoffs and other nearby structures if these need to be close to the sensor (:numref:`fig_A121_with_ebgs_lens_and_casing`). :numref:`fig_EBGs_farfields_with_lens_and_casing` shows how the side lobe level improve with the addition of EBGs, especially in the E-plane. Again, we observe a small increase in boresight gain (~2 dB) with the addition of EBGs.

.. _fig_EBGs_farfields_with_lens_and_casing:
.. figure:: /_static/hw_images/XS121-20-EBG_v1.1_with_lens_and_casing.svg
    :align: center
    :width: 100%

    Normalized far-fields with and without EBGs with lens and casing.

Mushroom type EBGs
==================

The EBGs used here are mushroom-type EBGs and these are one of the most common and effective structures. A mushroom unit cell consist of a square patch on the top layer with a centered metallic via connected to the ground plane underneath (layer 2), see :numref:`fig_EBG_schematic`. As multiple EBG cells are formed in an array, we obtain a periodic structure that can manipulate the material properties of the PCB. This allows us to create a spatial filter for suppressing surface currents as well as optimizing the PCB reflection phase.

Both blind vias and through hole vias can be used for constructing the EBG cells. The patch size, element spacing, dielectric thickness and dielectric properties are important tuning parameters for obtaining the desired performance.

.. _fig_EBG_schematic:
.. figure:: /_static/hw_images/EBG_top_and_side_views.svg
    :align: center
    :width: 95%

    Mushroom-type EBGs.


PCB guidelines with EBGs
========================

EBGs for 60 GHz are commonly implemented using RF PCB laminates. However, the EBG variants shown in :numref:`fig_XS121-20_EBG_eplane_3D` and :numref:`fig_XS121-20_EBG_ehplane_3D` are both using FR4 PCB materials to avoid adding material costs. This is possible by tuning the EBG dimensions to allow FR4 material tolerances and choosing specific stackups.

When laying out a PCB, the preferred way is to place all external components such as decoupling capacitors and crystal on the opposite side of the sensor as this typically results in the highest directivity and lowest side lobe level. In addition, to maximize the radiated performance, consider the following:

- Layer 2 must be a solid ground plane without routing where the EBGs are applied.
- The EBGs have been optimized for 0.20 - 0.25 mm via diameters. This also allows placing signal vias close to the footprint pads.
- Minimize the amount of routing on the sensor layer, at least within the clearance region in :numref:`fig_a121_pcb_front_side_components_3D`. This can be done by routing the signals to the sensor with vias placed as close as possible to the sensor pads, see :numref:`fig_a121_pcb_back_side_components`. The ground plane area inside the footprint has lower impact on the radiated performance and therefore some vias and short traces are preferably placed there.
- Whenever the assembly process allows, remove thermal reliefs on all sensor pads.
- Minimize copper clearance for traces, vias, and pads on the sensor layer to maximize the ground plane area close to the sensor.
- Add stitching vias with <0.6 mm spacing at the PCB outer edge to suppress potential edge radiation.
- Contact Acconeer support to obtain more information on EBG implementations.

The exact location and dimensions of the EBG cells are important for optimal performance. When using through-hole vias, signals can be routed between the EBG vias on layer 3 and below, see :numref:`fig_XS121_ebg_routing_example`. The E-plane only variant allows more routing area with a small loss in SLL performance. Occasionally, some EBG vias may need to be slightly shifted or removed to fit other signals and components. When this is needed, it is strongly recommended to do this on EBGs farthest away from the sensor as the innermost elements are most important.

.. _fig_XS121_ebg_routing_example:
.. figure:: /_static/hw_images/XS121_ebg_routing.svg
    :align: center
    :width: 75%

    Example mushroom type EBG implementation with routing.

More information
================

EBGs can be implemented using both low-cost FR-4 as well as RF PCBs. To implement EBG structures into your design, please contact the `Acconeer customer support <customer_support_>`_ for layout recommendations.

.. _customer_support: https://support.acconeer.com

