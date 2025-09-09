.. _integration-a121-EM_PCB:

==============================
PCB guidelines
==============================

In addition to electrical integration, the electromagnetic environment is important for optimal performance. The A121 pulsed coherent radar sensor is a fully integrated 60 GHz radar sensor with integrated transmitter and receiver antennas. The Tx and Rx antennas are folded-dipole type and the E-plane and H-planes are indicated in :numref:`fig_a121_polarization`. The :term:`RLG` patterns can be found in the `A121 Datasheet <a121_datasheet_>`_.

.. _fig_a121_polarization:
.. figure:: /_static/handbook/a121/in-depth_topics/integration/A121_polarization.png
    :align: center
    :width: 95%

    Sensor mounted on a printed circuit board (PCB). E-plane and H-plane are highlighted with blue and red color, respectively.


Radar loop equation
===================

Consider a signal transmitted through free space to a radar target located at distance :math:`R` from the radar. Assume there are no obstructions between the radar and the radar target, and the signal propagates along a straight line between the two. The channel model associated with this transmission is called a :term:`line-of-sight (LOS)<LOS>` channel. For the LOS channel, the corresponding received reflected power from a radar target, i.e. the :term:`signal-to-noise ratio (SNR)<SNR>`, can be defined as

.. math::
    :label: eq_snr

    SNR=C \sigma \gamma \frac{1}{R^{4}}

Where :math:`R` is the distance of the radar to the target, :math:`C` is the :term:`radar loop gain<RLG>`, including both the transmitter and receiver chain (two-ways signal path), :math:`\sigma` is the :term:`Radar Cross Section (RCS)<Radar Cross Section>` of the scattering object and :math:`\gamma` determines the reflected power of the object's material. :term:`RCS<Radar Cross Section>` depends on the size and shape of the scattering object. Moreover, :term:`SNR` depends on the sensor profile setting. A comprehensive explanation of the sensor profiles can be found under section :ref:`rdac-a121-profiles`.

Radar loop gain pattern
=======================

When characterizing the gain, we refer to the radar loop gain defined in the radar equation section. :numref:`fig_a111_RLG_setup` shows the radar setup configuration for the radar loop radiation pattern measurement. The reflector which in this case is a circular trihedral corner is located at the :term:`far-field<Far-field>` distance from the sensor.

The *Sparse IQ* service, see :ref:`interpreting_radar_data`, can be used to collect the reflected signal at the fixed distance from the radar target for different rotation angles. The figure of merit for amplitude variation stated in the document is the :term:`RLG` which includes both transmitter and receiver gain of the radar.

.. _fig_a111_RLG_setup:
.. figure:: /_static/handbook/a121/in-depth_topics/integration/A111_rlg_measurement_setup.png
    :align: center
    :width: 95%

    Measurement setup for :term:`RLG` radiation pattern.


PCB Layout
==========

.. _integration-a121-EM_PCB_groundplane_size:

Sensor ground plane size
------------------------

To maximize the :term:`RLG` and minimize impact on the radiation pattern, it is recommended that the top PCB layer is a filled copper layer with minimum amount of routing close to the sensor. :numref:`fig_gain_vs_groundplanesize_v2` shows the relative loss in :term:`RLG` as a function of ground plane size, assuming a solid square ground plane and the sensor placed at the center. As the ground plane size is increased, the :term:`RLG` increases because of increased antenna directivity. However, the :term:`RLG` does not increase monotonically with ground plane size due to constructive and destructive interference.

.. _fig_gain_vs_groundplanesize_v2:
.. figure:: /_static/handbook/a121/in-depth_topics/integration/A121_groundplane_size_simulation_with_sensor.png
    :align: center
    :width: 95%

    Simulated relative radar loop gain as function of ground plane side length (x). Ground plane is a solid square ground plane without routing.

In terms of regulatory compliance, any openings in the ground plane inside the A121 BGA footprint must be significantly smaller than the wavelength of the radiation that is being blocked, to effectively approximate an unbroken conducting surface.

.. _integration-a121-EM_PCB_component_placement:

Impact of PCB routing and nearby components
-------------------------------------------

As no RF components are required for the sensor integration, low-cost FR-4 type PCBs can generally be used. However, for a symmetrical :term:`RLG` pattern and maximum directivity, the following PCB design rules should be considered.

- Whenever possible, place decoupling capacitors and the crystal on the opposite side of the PCB. In other cases, the decoupling capacitors can be placed as in :numref:`a1_routing_b` and the crystal placed some distance away from the sensor. A small :term:`RLG` loss of approximately 0.5 dB is seen when placing decoupling capacitors (metric 1005 or smaller), see :numref:`fig_radiation_pattern_vs_groundpads`.
- Minimize the amount of routing close to the sensor. This can be done by routing the signals to the sensor with vias placed as close as possible to the sensor pads as shown in :numref:`a1_routing_a`. The ground plane area inside the footprint has lower impact on the radiated performance and therefore some vias and short traces are preferably placed there while still satisfying regulatory compliance.
- Minimize copper clearance for traces, vias, and pads on the sensor layer.
- If the PCB assembly allows, connect all ground pads without thermal reliefs as shown in :numref:`a1_routing_a` and :numref:`a1_routing_b`. This can increase the boresight :term:`RLG` by approximately 1.5 dB compared to :numref:`a1_routing_c`, provided there are no other interfering components or PCB traces close to the sensor, see :numref:`fig_radiation_pattern_vs_groundpads`.

.. grid:: 3
   :gutter: 1

   .. grid-item::

      .. _a1_routing_a:
      .. figure:: /_static/handbook/a121/in-depth_topics/integration/A1_routing_a.png
         :alt: Routing example with vias close to sensor
         :width: 100%

         Routing example with vias close to sensor

   .. grid-item::

      .. _a1_routing_b:
      .. figure:: /_static/handbook/a121/in-depth_topics/integration/A1_routing_b.png
         :alt: Routing example with decoupling capacitors and without GND thermal reliefs
         :width: 100%

         Routing example with decoupling capacitors and without GND thermal reliefs

   .. grid-item::

      .. _a1_routing_c:
      .. figure:: /_static/handbook/a121/in-depth_topics/integration/A1_routing_c.png
         :alt: Routing example with thermal reliefs
         :width: 100%

         Routing example with with GND thermal reliefs. Trace copper clearance is 0.127 mm

.. _fig_radiation_pattern_vs_groundpads:
.. figure:: /_static/handbook/a121/in-depth_topics/integration/ground_pad_simulation.svg
    :align: center
    :width: 95%

    Relative :term:`RLG` loss with and without thermal reliefs.

Impact of conformal coating
===========================

Conformal coating may be used to protect the sensor and other electronic components from environmental factors such as moisture, dust, and chemicals. Conformal coatings are typically made of polymeric materials with :term:`dielectric constants<Permittivity>` in the range :math:`\varepsilon_r` < 4. Depending on the coating material properties and layer thickness, the sensor's :term:`RLG` may decrease. This gain drop is due to three factors:

1. Offset in antenna resonance frequency as the antenna becomes electrically larger.
2. :term:`Reflection` and :term:`refraction<Refraction>` loss due to the interface between the sensor and the coating.
3. Dielectric loss in the coating material. This can usually be neglected for this coating layers (e.g. < 200 :math:`\mathrm{\mu m}`).

:numref:`fig_conformal_coating_gain_vs_thickness_Dk` shows the simulated relative :term:`RLG` after a linear lossless (tan(:math:`\mathrm{\delta}`) = 0) isotropic coating has been added to all sides of the radar sensor. As the coating thickness increases and/or the :term:`dielectric constant<Permittivity>` increases, the :term:`RLG` decreases. However, this loss is non-monotonic, and this is due to constructive and destructive interference depending on the coating thickness.

The loss due to antenna resonance frequency offset can be seen in :numref:`fig_conformal_coating_gain_vs_thickness_Dk2` and :numref:`fig_conformal_coating_gain_vs_thickness_Dk3` where the maximum gain is shifted in frequency. This means that, as the radar signal is a wideband signal, the resulting loss in :term:`SNR` can be expected to be somewhat less than what is estimated in those.

If it is critical to obtain the maximum gain, it is recommended to use a thin coating layer (< 40 :math:`\mathrm{\mu m}`) with a low :term:`dielectric constant<Permittivity>` and loss factor. As many coating materials are not well characterized at mmWave frequencies. performance should be verified with actual tests.

.. _fig_conformal_coating_gain_vs_thickness_Dk:
.. figure:: /_static/handbook/a121/in-depth_topics/integration/conformal_coating_vs_Dk.svg
    :align: center
    :width: 95%

    Simulated impact of lossless dielectric conformal coating on :term:`RLG` at 60 GHz.



.. grid:: 2
   :gutter: 2

   .. grid-item::

      .. _fig_conformal_coating_gain_vs_thickness_Dk2:
      .. figure:: /_static/handbook/a121/in-depth_topics/integration/conformal_coating_vs_thickness_Dk2.svg
         :alt: Dk 2
         :width: 100%

         Simulated impact of conformal coating with :math:`\varepsilon_r = 2` and varying thickness

   .. grid-item::

      .. _fig_conformal_coating_gain_vs_thickness_Dk3:
      .. figure:: /_static/handbook/a121/in-depth_topics/integration/conformal_coating_vs_thickness_Dk3.svg
         :alt: Dk 3
         :width: 100%

         Simulated impact of conformal coating with :math:`\varepsilon_r = 3` and varying thickness





For more information, see:

* :octicon:`download` `A121 Datasheet <a121_datasheet_>`_
* :octicon:`download` `Hardware integration guideline <a121_hw_integration_guideline_>`_, in section *Electromagnetic Integration*

.. _a121_datasheet: https://developer.acconeer.com/download/A121-datasheet
.. _a121_hw_integration_guideline: https://developer.acconeer.com/download/Hardware-integration-guideline
