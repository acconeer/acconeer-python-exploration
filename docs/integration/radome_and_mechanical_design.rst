.. _integration-a121-radomes:

============================
Radome and mechanical design
============================

A radome is the product housing or plastic cover in front of the radar that protects it from mechanical impact and weather, see :numref:`fig_transmissionreflection`. When designed correctly, the radome is effectively transparent to the radar signal and thus not impacting the radiated performance.

Transmission and reflection
===========================

When an electromagnetic (EM) wave hits the interface between two :term:`dielectrics<Dielectric>`, such as plastic and air, :term:`reflection<Reflection>` and :term:`refraction<Refraction>` occur at the boundary. Inside the :term:`dielectric<Dielectric>`, the propagation speed and wavelength change depending on the material’s :term:`permittivity<Permittivity>`. If the wavelength in free space is :math:`\lambda_{0}`, 5 mm at 60 GHz, the wavelength inside the material is :math:`\lambda=\frac{\lambda_{0}}{\sqrt{\varepsilon_r}}`, where :math:`\varepsilon_r` is the relative :term:`dielectric constant<Permittivity>` of the material.

In the case of :term:`linearly polarized<Linear polarization>` propagation at :term:`normal incidence<Normal incidence>`, the Fresnel equations relate the ratio between the incident and transmitted fields:

.. math::
    :label: eq_transmissionreflection

    r=\frac{Z_{2} - Z_{1}}{Z_{2} + Z_{1}}, \quad t=\frac{2Z_{2}}{Z_{2}+Z_{1}},

where :math:`Z_{1}` and :math:`Z_{2}` are the corresponding wave impedances. The :term:`transmission<Transmission>` and :term:`reflection<Reflection>` factors are also related by :math:`t = 1 + r`. In most cases, we have non-magnetic materials so that :math:`Z = \sqrt{\frac{\mu_{r}}{\varepsilon_r}} = \frac{1}{\sqrt{\varepsilon_r}}`. An important special case is :term:`normal incidence<Normal incidence>` between air and a :term:`dielectric<Dielectric>`. The reflection coefficient then simplifies to

.. math::
    :label: eq_airdielectricreflection

    r=\frac{1 - \sqrt{\varepsilon_r}}{1 + \sqrt{\varepsilon_r}}

From this expression, we can see that the materials with a higher :term:`dielectric constant<Permittivity>` produce stronger reflections of the incidence signal. Conductors, such as metal, have a very high :term:`dielectric constant<Permittivity>` (:math:`\varepsilon_r \rightarrow \infty`) and thus produce a strong :term:`reflection<Reflection>`. Most polymers have a :term:`dielectric constant<Permittivity>` in the range 2–4, and therefore give a weaker :term:`reflection<Reflection>`.

Radomes
=======

Radome thickness
----------------

Let :math:`d_1` be the distance to the radome, :math:`d_2` the thickness, :math:`r_1` and :math:`r_2` the reflection coefficients, and :math:`t_1` and :math:`t_2` the corresponding transmission coefficients according to :numref:`fig_transmissionreflection`. As an incident wave hits the first interface, a :term:`reflection<Reflection>` :math:`r_1`, and a :term:`transmission<Transmission>` :math:`t_1` occur. Note that :math:`r_1 < 1`, so the reflected wave is out of phase with the incident wave. At the second interface, another :term:`reflection<Reflection>` :math:`r_2` and :term:`transmission<Transmission>` :math:`t_2` take place. With air on both sides of the :term:`dielectric<Dielectric>`, note from :eq:`eq_transmissionreflection` that :math:`r_1 = -r_2`. The total reflection coefficient :math:`\Gamma_1` then becomes [#f1]_:

.. math::
    :label: eq_reflectioncoeff

    \Gamma_{1}=\frac{r_{1} \left(1 - e^{-2jkd_{2}}\right)}{1 - r_{1}^{2} e^{-2jkd_{2}}}

where :math:`k = 2\pi/\lambda` is the wave number in the material. Two notable special cases follow:

- For :math:`d_{2} = m\frac{\lambda}{2}, \; m = 1,2,...` we have :math:`e^{-2jk d_{2}}=1` and :math:`\Gamma_{1} = 0`.
- For :math:`d_{2} = m\frac{\lambda}{4}, \; m = 1,3,5,...` we have :math:`e^{-2jk d_{2}}=-1` and :math:`\Gamma_{1} = \frac{2r_{1}}{1+r_{1}^{2}}`.

The optimum radome thickness occurs when the :term:`dielectric<Dielectric>` is perfectly :term:`reflectionless<Reflection>`, i.e. when the thickness is a multiple of half a wavelength. This can also be understood from the fact that the round trip of the wave inside the radome introduces a 360° phase shift, thereby cancelling the reflected wave :math:`r_{1}`.

.. _fig_transmissionreflection:
.. figure:: /_static/handbook/a121/in-depth_topics/integration/radome_transmission_and_reflection.svg
    :align: center
    :width: 95%

    :term:`Transmitted<Transmission>` and :term:`reflected<Reflection>` signals from a half-wavelength radome. Secondary :term:`reflections<Reflection>` have been omitted for simplicity.

As an example, if the material is polycarbonate with relative :term:`permittivity<Permittivity>` :math:`\varepsilon_r=2.75`, the optimal radome thickness becomes:

.. math::
    :label: eq_exthicknesscalc

    d_{2}=m\frac{\lambda}{2} = m\frac{\lambda_{0}}{2\sqrt{\varepsilon_r}}
    = m\frac{5}{2\sqrt{2.75}} \approx m \times 1.51 \:\mathrm{mm}, m = 1,2,...

If the :term:`dielectric<Dielectric>` thickness is an odd multiple of :math:`\frac{\lambda}{4}`, maximum :term:`reflection<Reflection>` occurs. The relative :term:`dielectric constant<Permittivity>` of some more materials can be found in :numref:`tab_common_material`.

Radome distance
---------------

In addition to radome thickness, the distance between the sensor and the radome also affects performance. Depending on the radome thickness and distance, the initial :term:`reflection<Reflection>` from the radome will cause multiple :term:`reflections<Reflection>` between the sensor, PCB, and radome. This leads to a standing-wave pattern where the amplitude varies as a function of radome distance. The amplitude variation will be minimal if the reflected wave from the radome is in phase with the transmitted wave. The optimum radome distance is

.. math::
    :label: eq_radomedistance

    d_{1}=m\frac{\lambda_{0}}{2}, \quad m = 1,2,3,...

Figure :numref:`fig_radomethicknessvdistance` shows the measured amplitude variations of the reflected wave from a radar target when the distance between the sensor and the radome is varied for different radome thicknesses. The radome has a :term:`dielectric constant<Permittivity>` of :math:`\varepsilon_r=2.6`, so the optimum thickness is :math:`d_{2} = 1.55 \approx 1.6 \:\mathrm{mm}`, which shows the minimum amplitude variation. When the radome thickness is a multiple of :math:`\frac{\lambda}{4} = \frac{3.1}{4} \approx 0.7 \:\mathrm{mm}`, the maximum amplitude variation is observed as a function of distance.

.. _fig_radomethicknessvdistance:
.. figure:: /_static/handbook/a121/in-depth_topics/integration/radome_thickness_vs_distance_A121.png
    :align: center
    :width: 95%

    Amplitude vs. radome thickness and distance. Amplitude variation is shown for a single direction (Tx or Rx). For combined Tx+Rx, the values are doubled.


If absolute distance measurements are required for a particular use case, an additional offset should be applied. This offset compensates for the propagation delay introduced by the radome. It can be determined through reference measurements, and also allows the reference plane to be positioned at the desired location within the product. For multi-layer radome optimization, see [#f1]_.


Dielectric constant of common materials
=======================================

The :term:`dielectric constant<Permittivity>` of some common polymers at 60 GHz is presented in :numref:`tab_common_material`.

.. _tab_common_material:
.. table:: Relative :term:`permittivity<Permittivity>` of common materials [#f2]_
    :align: center
    :widths: auto

    ==================================== =====================================
    Material                             Re(:math:`\varepsilon`) at 60 GHz
    ==================================== =====================================
    Acrylic glass                        2.5
    Alumina                              9.3
    Fused Quartz                         3.8
    MACOR                                5.5
    PEEK                                 3.12 [#f3]_
    PMMA                                 2.6  [#f4]_
    Polycarbonate (PC)                   2.75 [#f4]_ [#f5]_
    Polyethylene (PE)                    2.3  [#f5]_ [#f6]_ [#f7]_ [#f8]_
    Polypropylene (PP)                   2.2  [#f5]_ [#f8]_
    Polystyrene (Rexolite)               2.5
    PTFE (Teflon)                        2.05 [#f5]_
    ==================================== =====================================


.. rubric:: Footnotes

.. [#f1]
   S. J. Orfanidis, *Electromagnetic Waves and Antennas*,
   New Jersey: Rutgers University, 2016.

.. [#f2]
   S. R. Artem Boriskin, *Aperture Antennas for Millimeter and Sub-Millimeter Wave Applications*,
   Springer, 2017.

.. [#f3]
   N. C. F. T. V. et al., "Complex Dielectric Permittivity of Engineering and 3D-Printing Polymers at Q-Band,"
   *J. Infrared Milli Terahz Waves*, vol. 39, pp. 1140–1147, 2018.

.. [#f4]
   B. L. G. et al., "A Comparison of Measurements of the Permittivity and Loss Angle of Polymers in the Frequency Range 10 GHz to 90 GHz,"
   *2021 15th European Conference on Antennas and Propagation (EuCAP)*, pp. 1–5, 2021.

.. [#f5]
   Y. O. K. F. M. M. K. S. Yuka Hasegawa, "Complex Permittivity Spectra of Various Insulating Polymers at Ultrawide-Band Frequencies,"
   *Electrical Engineering in Japan*, vol. 198, no. 3, pp. 11–18, 2017.

.. [#f6]
   J. W. Lamb, *Miscellaneous Data on Materials for Millimetre and Submillimetre Optics*.

.. [#f7]
   Salski et al., "Complex Permittivity of Common Dielectrics in 20–110 GHz Frequency Range Measured with a Fabry–Perot Open Resonator."

.. [#f8]
   Afsar et al., "A New 60 GHz Open-Resonator Technique for Precision Permittivity and Loss-Tangent Measurement."
