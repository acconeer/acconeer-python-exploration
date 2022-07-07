Performance metrics
===================

Radar sensor performance metrics (RSPMs) for the Acconeer radar system provides useful information on the performance of the system: sensor, RSS and reference integration. The list contains the RSPMs that are applicable to services that produce radar data. However, not all RSPMs are applicable to all radar services. The RSPMs is used in our `Radar Datasheet <https://developer.acconeer.com/download/a111-datasheet-pdf/>`__.


Radar loop gain
---------------

The SNR can be modelled as a function of a limited number of parameters: the RCS of the object (:math:`\sigma`), the distance to the object (:math:`R`), the reflectivity of the object (:math:`\gamma`), and a radar sensor dependent constant referred to as radar loop gain (:math:`C`). The SNR (in dB) is then given by

.. math::
    :label: eq_radar_eq

    \mathrm{SNR}_{dB}=10\log_{10}\frac{S}{N}=C_{dB}+\sigma_{dB}+\gamma_{dB}-k10\log_{10}R

:numref:`fig_rx_power_vs_dist` shows how the received energy drops with increasing :math:`R` for objects where the exponent :math:`k` is equal to 4, which applies for objects which are smaller than the area which is illuminated coherently by the radar. For objects that are larger than this area the :math:`k` is smaller than 4, with a lower limit of :math:`k = 2`  when the object is a large flat surface.

.. _fig_rx_power_vs_dist:
.. figure:: /_static/introduction/fig_rx_power_vs_dist.png
    :align: center

    Received signal power versus distance. Note: signal, S, is plotted in dB.


Depth resolution
----------------

The depth resolution determines the minimum distance of two different objects in order to be distinguished from each other.


Distance resolution
-------------------

The Acconeer radar systems are based on a time diluted measurement that splits up as a vector of energy in several time bins it is important to know the bin separation. This is the delay resolution of the system and in A111 radar sensor the target is ~3 ps on average, which corresponds to a distance resolution of ~0.5 mm between distance samples.


Half-power beamwidth
--------------------

The half-power beamwidth (HPBW) radiation pattern determines the angle between the half-power (-3 dB) points of the main lobe of the radiation pattern. The radiation pattern of the sensor depends on both the antenna-in-package design and the hardware integration of the sensor, such as surrounding components, ground plane size, and added di-electric lenses for directivity optimizations, valid for both vertical and horizontal plane.


Distance jitter
---------------

The distance jitter determines the timing accuracy and stability of the radar system between sweep updates. The jitter is estimated by calculating the standard deviation of the phase, for the same distance bin, over many IQ sweeps.


Distance linearity
------------------

The distance linearity deterministic the deterministic error from the ideal delay transfer function. Linearity of the service data is estimated by measuring the phase change of the IQ data vs distance.


Update rate accuracy
--------------------

The update rate accuracy determines the accuracy of the time between sweep updates or similarly the accuracy of the update rate, typically important when the radar data is used for estimating velocity of an object.


Close-in range
--------------

The close-in range determines the radar system limits on how close to the radar sensor objects can be measured.


Power consumption
-----------------

The power consumption determines the radar sensor power usage for different configurations as service depends, the power save mode, the update rate, downsampling, sweep length, etc.
