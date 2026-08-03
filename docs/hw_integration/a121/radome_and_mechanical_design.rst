.. _integration-a121-radomes:

============================
Radome and mechanical design
============================

This chapter covers the EM design considerations for radomes used with A121, including thickness and placement optimization. A radome is the product enclosure or plastic cover in front of the radar that protects it from mechanical impact and weather, see :numref:`fig_a121_spherical_enclosure`. When designed correctly, the radome is effectively transparent to the radar signal, as discussed below. Note that in applications where a dielectric lens is used, no additional radome is needed.

.. _fig_a121_spherical_enclosure:
.. figure:: /_static/hw_images/A121_pcb_and_spherical_radome.png
    :align: center
    :width: 75%

    Example enclosure with curved or spherical radome.

Transmission and reflection
===========================

When an electromagnetic (EM) wave hits the interface between two :term:`dielectrics<Dielectric>`, such as plastic and air, :term:`reflection<Reflection>` and :term:`refraction<Refraction>` occur at the boundary. Inside the dielectric, the propagation speed and wavelength change depending on the material’s :term:`permittivity<Permittivity>`. If the wavelength in free space is :math:`\lambda_{0}` (5 mm at 60 GHz), the wavelength inside the material is :math:`\lambda=\frac{\lambda_{0}}{\sqrt{\varepsilon_r}}`, where :math:`\varepsilon_r` is the relative permittivity or :term:`dielectric constant<Permittivity>` of the material.

In the case of :term:`linearly polarized<Linear polarization>` propagation at :term:`normal incidence<Normal incidence>`, the Fresnel equations relate the ratio between the incident and transmitted fields:

.. math::
    :label: eq_transmission_reflection

    r=\frac{Z_{2} - Z_{1}}{Z_{2} + Z_{1}}, \quad t=\frac{2Z_{2}}{Z_{2}+Z_{1}},

where :math:`Z_{1}` and :math:`Z_{2}` are the corresponding wave impedances. Most often we have non-magnetic materials :math:`(\mu_{r}=1)` so that :math:`Z = \sqrt{\frac{\mu_{r}}{\varepsilon_r}} = \frac{1}{\sqrt{\varepsilon_r}}`. An important special case is normal incidence between air and a dielectric. The reflection coefficient then simplifies to

.. math::
    :label: eq_air_dielectric_reflection

    r=\frac{1 - \sqrt{\varepsilon_r}}{1 + \sqrt{\varepsilon_r}}

From this expression, we can see that materials with a higher dielectric constant produce stronger reflections. Conductors, such as metal, have very high dielectric constants (:math:`\varepsilon_r \rightarrow \infty`) and thus produce a strong reflection. Most polymers have a dielectric constant in the range 2–4, and therefore give a weaker reflection.

Radome design
=============

Without a lens or horn antenna, the A121 behaves as a hemispherical source with a wide field of view (FoV). To preserve the radiation pattern, a curved or spherical radome with a fixed thickness is ideal as every ray hits the radome at normal incidence over all angles (:numref:`fig_a121_spherical_enclosure`). However, planar radomes (:numref:`fig_a121_planar_enclosure`) are commonly preferred from a product design standpoint, and when properly designed, these radomes have negligible impact on the radiation pattern. We will in the following discuss how to optimize these radomes.

.. _fig_a121_planar_enclosure:
.. figure:: /_static/hw_images/A121_pcb_and_planar_radome.png
    :align: center
    :width: 75%

    Example enclosure with planar radome.

.. _integration-a121-radome-thickness:

Radome thickness
----------------

To minimize reflection losses and unwanted interference, the radome thickness needs to be chosen properly. Let :math:`d_1` be the distance to the radome, :math:`d_2` the radome thickness, :math:`r_1` and :math:`r_2` the reflection coefficients, and :math:`t_1` and :math:`t_2` the corresponding transmission coefficients according to :numref:`fig_transmission_reflection`. As an incident wave hits the first interface, a reflection :math:`r_1` and a transmission :math:`t_1` occur. At the second interface, another reflection :math:`r_2` and transmission :math:`t_2` take place. With air on both sides of the dielectric, it follows from :eq:`eq_transmission_reflection` that :math:`r_1 = -r_2`. The total reflection coefficient :math:`\Gamma_1` then becomes [1]_:

.. math::
    :label: eq_reflection_coeff

    \Gamma_{1}=\frac{r_{1} \left(1 - e^{-2jkd_{2}}\right)}{1 - r_{1}^{2} e^{-2jkd_{2}}}

where :math:`k = 2\pi/\lambda` is the wave number in the material. Two notable special cases follow. First, for the half-wavelength condition:

.. math::
    :label: eq_half_wavelength_condition

    d_{2} = m\frac{\lambda}{2}, \quad m = 1,2,...

we have :math:`e^{-2jkd_{2}}=1`, and the reflection coefficient vanishes or :math:`\Gamma_{1} = 0`.

Second, for the quarter-wavelength condition:

.. math::
    :label: eq_quarter_wavelength_condition

    d_{2} = m\frac{\lambda}{4}, \quad m = 1,3,5,...

we have :math:`e^{-2jkd_{2}}=-1`, and the reflection coefficient reaches its maximum or :math:`\Gamma_{1} = \frac{2r_{1}}{1+r_{1}^{2}}`.

.. _fig_transmission_reflection:
.. figure:: /_static/hw_images/radome_transmission_and_reflection.svg
    :align: center
    :width: 60%

    Transmitted and reflected signals from a half-wavelength radome. Some secondary reflections have been omitted for simplicity.

Thus the dielectric is perfectly :term:`reflectionless<Reflection>` when the thickness is a multiple of half a wavelength (:eq:`eq_half_wavelength_condition`). This can also be understood from the fact that the round trip of the wave inside the radome introduces a 360° phase shift, thereby cancelling the reflected wave :math:`r_{1}`.

Example radome
--------------

The far-field patterns for a few example radomes using polycarbonate (PC) are shown in :numref:`fig_a121_planar_and_spherical_radomes`. For PC, :math:`\varepsilon_r=2.8` at 60 GHz and the optimal radome thickness becomes (:eq:`eq_half_wavelength_condition`):

.. math::

    d_{2}=m\frac{\lambda}{2} = m\frac{\lambda_{0}}{2\sqrt{\varepsilon_r}}
    = m\frac{5}{2\sqrt{2.8}} \approx m \times 1.5 \:\mathrm{mm}, m = 1,2,...

The above corresponds to the orange curve in :numref:`fig_a121_planar_and_spherical_radomes`. As the radome thickness is close to optimal, little or no gain loss is observed. Some small pattern distortion occurs as the A121 spherical wavefront refracts and reflects in a planar radome. With a spherical radome (red curve), the far-field pattern closely follows that in free space (blue curve). Spherical radomes should be considered when low sidelobe level is of importance.

If the dielectric thickness is an odd multiple of :math:`\lambda/4`, maximum reflection occurs (:eq:`eq_quarter_wavelength_condition`). This is also shown in :numref:`fig_a121_planar_and_spherical_radomes` (green curve) where the planar radome thickness is :math:`3\lambda/4` =2.25 mm. This results in significant pattern interference and gain loss. The importance of properly choosing the radome thickness has thus been demonstrated.

.. _fig_a121_planar_and_spherical_radomes:
.. figure:: /_static/hw_images/A121_gain_vs_radomes.svg
    :align: center
    :width: 100%

    Simulated far-fields with half-wavelength (:math:`\lambda/2` =1.5 mm) and quarter-wavelength (:math:`3\lambda/4` =2.25 mm) planar and spherical radomes.

Radome distance
---------------

When using (half-wavelength) planar radomes, some back reflection occurs for angles away from boresight. These reflections cause standing waves between the sensor, the PCB and the radome which result in main beam ripple. This can be minimized by tuning the distance between the radome and the sensor.

:numref:`fig_planar_radome_distance` shows the simulated far-field pattern for a half-wavelength planar radome with :math:`\varepsilon_r=2.8` for different radome distances. When the radome distance is 3.0 - 3.5 mm (with respect to PCB ground plane), minimum pattern ripple is observed. This corresponds to a distance of :math:`\sim\lambda_{0}/2` between the sensor and radome.

.. _fig_planar_radome_distance:
.. figure:: /_static/hw_images/A121_gain_vs_planar_radome_distance.svg
    :align: center
    :width: 100%

    Simulated far-fields of half-wavelength (1.5 mm) planar radome for different distances. All distances with respect to PCB ground plane.

If absolute distance measurements are required, an additional offset should be applied to compensate for the propagation delay introduced by the radome. This offset can be determined through reference measurements or by calculating the propagation delay in the dielectric.

For more advanced radomes such as multilayer radome design and custom radome shapes, please contact the `Acconeer customer support <customer_support_>`_ for design assistance.

.. _customer_support: https://support.acconeer.com

Summary
-------

- To avoid reflection losses and pattern interference, the radome thickness should be a multiple of :math:`\lambda/2`.
- Both curved and planar radomes can be used. When sidelobe level is of importance, curved radomes are recommended (e.g. R=20-50 mm).
- For half-wavelength planar radomes, the distance between the sensor and the radome should be a multiple of :math:`\lambda_{0}/2`. To minimize pattern ripple, radomes placed close to the sensor (2.5 mm) are preferred.

.. include:: ../common/dk_of_common_materials.rst

References
----------

.. [1]    S. J. Orfanidis, *Electromagnetic Waves and Antennas*,
   New Jersey: Rutgers University, 2016.

