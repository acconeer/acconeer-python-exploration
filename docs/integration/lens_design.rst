.. _integration-a121-lenses:

============
Lens design
============

:term:`Dielectric` lenses are a cost-effective way of shaping the radiation patterns, especially for mmWave applications where the size of the lens becomes small enough. Although it is most common to design lenses for increasing the gain and to narrow the beamwidth, lenses can also be used for increasing the beamwidth, produce tilted beams, or suppress side lobes to reject unwanted :term:`reflections<Reflection>`.

Since many common thermoplastics used in the product design also have low :term:`permittivity<Permittivity>` and low loss, a lens can often be incorporated into the same encapsulation material with little additional cost. 3D printing technology allows for rapid prototyping and can often resemble the performance of the final product. :term:`Dielectric` lenses are generally more compact and less expensive to fabricate than corresponding horn antennas and reflectors.

To quickly get started using a lens, Acconeer provides two example lenses, one plano-convex and one FZP type lens, :numref:`fig_module_plano-convex` and :numref:`fig_module_FZP`. Both lenses can be used with all module evaluation kits. The FZP lens is similar to the example lens in :ref:`integration-a121-lenses_example_FZP`. The user guide and performance of these lenses can be found in `A121 Lenses Getting Started Guide <a121_lens_guide_>`_.

.. grid:: 2
   :gutter: 2

   .. grid-item::

      .. _fig_module_plano-convex:
      .. figure:: /_static/handbook/a121/in-depth_topics/integration/module_plano_convex_lens.png
         :alt: Module plano-convex lens
         :width: 150%

         Plano-convex lens from Acconeer lens kit

   .. grid-item::

      .. _fig_module_FZP:
      .. figure:: /_static/handbook/a121/in-depth_topics/integration/FZP_module_lens.png
         :alt: Module FZP Lens
         :width: 65%

         FZP lens from Acconeer lens kit



Refracting lenses
=================

Design Principles
-----------------

:numref:`fig_hyperbolic_efield` shows a spherical wavefront from the A121 sensor feeding a converging lens of refractive index :math:`n = \sqrt{\varepsilon_r}`. The lens :term:`refracts<Refraction>` the spherical waves to produce parallel waves for increasing the directivity. :numref:`fig_hyperbolic_ray_model` shows the corresponding ray optics model where rays propagate from the source as diverging straight lines until hitting the first surface and :term:`refracting<Refraction>` into parallel rays. Ray optics does not account for interference, :term:`diffraction<Diffraction>`, and polarization but it provides a basic understanding of :term:`dielectric<Dielectric>` lenses, and most importantly, allows us to quickly construct analytical lens shapes for many applications.

In the following we assume that all lens profiles are axisymmetric, although asymmetrical lenses can be designed for customized radiation patterns. For a converging lens, two criteria need to be fulfilled:

1. :term:`Refraction` at one or both surfaces to produce parallel rays at the output.
2. The rays just outside the outer surface have to be coherent (in-phase).

One of the lens surfaces can be chosen arbitrarily, for example planar or spherical. Next, we will provide design equations for constructing converging lenses fulfilling these criteria.

.. grid:: 2
   :gutter: 2

   .. grid-item::

      .. _fig_hyperbolic_efield:
      .. figure:: /_static/handbook/a121/in-depth_topics/integration/hyperbolic_efield.png
         :alt: Hyperbolic E-field
         :width: 68%

         Hyperbolic lens with spherical E-field source

   .. grid-item::

      .. _fig_hyperbolic_ray_model:
      .. figure:: /_static/handbook/a121/in-depth_topics/integration/hyperbolic_ray_model.svg
         :alt: Hyperbolic ray model
         :width: 100%

         Hyperbolic lens ray model

Convex-planar lens (Hyperboloidal lens)
---------------------------------------

By constraining the outer surface to planar we have :math:`x_{2} = F + T`, :numref:`fig_hyperbolic_ray_model`. Equating the optical path through a point (:math:`x_{1},y_{1}`) with the central path yields

.. math::
    :label: eq_hyperbolic_1

    \sqrt{x_{1}^{2} + y_{1}^{2}} = nx_{1} + (1- n)F

:eq:`eq_hyperbolic_1` can be written as

.. math::
    :label: eq_hyperbolic_2

    \left(\frac{x_{1}-x_{0}}{a}\right)^{2} - \left(\frac{y_{1}}{b}\right)^{2} = 1


where the coefficients are given by

.. math::
    :label: eq_hyperbolic_3

    a = \frac{F}{n+1}, b = \sqrt{\frac{n-1}{n+1}}F, x_{0} = \frac{nF}{n+1}


Observe that we have :term:`refraction<Refraction>` only at the inner surface, that is, this is a single :term:`refracting<Refraction>` lens. We recognize :eq:`eq_hyperbolic_3` as a hyperbolic function shifted in the :math:`x` direction by :math:`x_{0}`, hence the name hyperbolic (2D) or hyperboloidal (3D) lens.

The central thickness of the lens can be shown to be

.. math::
    :label: eq_hyperbolic_4

    T = \frac{1}{n+1}\left( \sqrt{F^{2} + \frac{(n+1)D^{2}}{4(n-1)}} -F \right)

To generate a lens profile, we first choose a material :math:`n = \sqrt{\varepsilon_r}`. After this the diameter :math:`D` and the focal distance :math:`F` is chosen to fulfill some maximum thickness requirement in :eq:`eq_hyperbolic_4`. The lens profile is then given by :eq:`eq_hyperbolic_2` by solving for :math:`y_{1} = y_{1}(x_{1}), x_{1}\in [F, F+T]`. A parametrization :math:`(x_{1}(t),y_{1}(t))` may be required for generating the lens profile in CAD software. One such parametrization is

.. math::
    :label: eq_hyperbolic_parametric

    \begin{cases}
    x_{1} = x_{0}+a \sqrt{1 + \left( \frac{t}{b}\right)^{2}}\\
    y_{1} = t
    \end{cases}
    , t \in \left[-\frac{D}{2}, \frac{D}{2} \right]


Plano-convex lens
-----------------

Constraining the inner surface to planar results in a plano-convex lens, see :numref:`fig_plano-convex_ray_model`. We then have :math:`x_{1} = F` and carrying out the algebra results in the following parametric solution for the outer surface:

.. math::
    :label: eq_planoconvex_1

    \begin{cases}
    x_{2} = \frac{\left((n-1)T \sqrt{F^{2}+y_{1}^{2}}\right) \sqrt{(n^{2}-1)y_{1}^2 + n^{2}F^{2}} + n^{2}F\sqrt{F^{2}+y_{1}^{2}}}{n^{2}\sqrt{F^{2}+y_{1}^{2}} - \sqrt{(n^{2} - 1)y_{1}^{2} + n^{2}F^{2}}} \\
    y_{2} = y_{1}\left(1+\frac{x_{2}-F}{\sqrt{(n^{2} - 1)y_{1}^{2} + n^{2}F^{2}}} \right)
    \end{cases}

.. _fig_plano-convex_ray_model:
.. figure:: /_static/handbook/a121/in-depth_topics/integration/plano-convex_ray_model.svg
    :align: center
    :width: 95%

    Plano-convex lens ray model.

The central thickness is given by

.. math::
    :label: eq_planoconvex_2

    T = \frac{\sqrt{4F^{2} + D^{2}}-2F}{2(n-1)}

Contrary to the hyperboloidal lens, we now have :term:`refraction<Refraction>` at both the inner and the outer surfaces. The lens profile given in :eq:`eq_planoconvex_1` do not resemble any known function and we therefore simply call this lens a plano-convex lens.

Lens gain
=========

The lens gain is related to the lens effective area by :math:`G = \frac{4 \pi A_{e}}{\lambda^{2}}` where :math:`\lambda` is the wavelength in the :term:`dielectric<Dielectric>` material. Approximating the effective area with the lens inner surface area :math:`A_{e} = \pi \left(\frac{D}{2}\right)^{2}`, we obtain :math:`G = \left(\frac{\pi D}{\lambda}\right)^{2}`. We thus notice that the lens gain is proportional to the square of the diameter. To get the lens :term:`RLG`, we double the lens gain, because of the Tx and Rx path.

:numref:`fig_hyperbolic_gain_vs_size` and :numref:`fig_plano_convex_gain_vs_size` show simulated :term:`RLG` pattern plots for the hyperbolic and the plano-convex lenses for some sample values of F and D. These figures can be used as a rough guideline for choosing the lens size. Observe that for the same diameter, the plano-convex lens yields somewhat higher gain compared to the hyperbolic lens. The exact :term:`RLG` pattern will also depend on the lens housing, choice of material, and PCB size.

.. _fig_hyperbolic_gain_vs_size:
.. figure:: /_static/handbook/a121/in-depth_topics/integration/hyperbolic_size_vs_gain.svg
    :align: center
    :width: 95%

    Simulated :term:`RLG` patterns for different size hyperbolic lenses assuming lossless :term:`dielectrics<Dielectric>`.

.. _fig_plano_convex_gain_vs_size:
.. figure:: /_static/handbook/a121/in-depth_topics/integration/Plano-convex_size_vs_gain.svg
    :align: center
    :width: 95%

    Simulated :term:`RLG` patterns for different size plano-convex lenses assuming lossless :term:`dielectrics<Dielectric>`.


Fresnel Zone Plate (FZP) lenses
================================

The plano-convex and convex-planar type lenses are :term:`refracting<Refraction>` type lenses. Another popular lens type is the Fresnel zone plate lens which is based on :term:`diffraction<Diffraction>` instead of :term:`refraction<Refraction>`. Different types of FZP lenses exists and here the phase correcting FZP lens is covered. The FZP lens structure is composed of :term:`dielectric<Dielectric>` rings with different thickness for correcting the phase of the incident waves. :numref:`fig_fzp_ray_model` shows an example of FZP lens consisting of 3 zones with the phase step of quarter of a wavelength.

.. grid:: 2
   :gutter: 2

   .. grid-item::

      .. _fig_fzp_ray_model:
      .. figure:: /_static/handbook/a121/in-depth_topics/integration/FZP_ray_model.png
         :alt: FZP Ray model
         :width: 100%

         FZP lens drawing

   .. grid-item::

      .. _fig_FZP_efield:
      .. figure:: /_static/handbook/a121/in-depth_topics/integration/FZP_efield.png
         :alt: FZP E-field
         :width: 92%

         FZP Lens with spherical E-field source

The radius :math:`r_{i}` of the rings and the step thickness :math:`s` can be calculated with:

.. math::
    :label: eq_FZP_1

    r_{i} = \sqrt{2Fi\frac{\lambda_{0}}{p} + \left(\frac{i\lambda_{0}}{P}\right)^{2}}, i = 1,2,3,...., N


.. math::
    :label: eq_FZP_2

    s = \frac{\lambda}{P\left(\sqrt{\varepsilon_r} -1\right)}


Here :math:`F` is the focal point, :math:`P` is the number of sub-zones, or steps, :math:`\lambda_{0}` is the wavelength in free space ( 5 mm at 60 GHz), and :math:`\varepsilon_r`, is the :term:`relative dielectric constant<Permittivity>`. For small diameter lenses, we can choose one zone and 4 or 8 steps. For larger diameter lenses, additional sub-zones can be added for increased gain. Notice that contrary to the :term:`refracting<Refraction>` type lenses, the ring thickness and hence the total thickness is independent of the lens radius. This allows us to construct large diameter lenses without increasing the thickness.

.. _integration-a121-lenses_example_FZP:

Example FZP lens calculation
----------------------------

This is an example of a single zone FZP lens with a focal point F = 10 mm and quarter of wavelength step, N = 4. We assume material :term:`permittivity<Permittivity>` of :math:`\varepsilon_r` = 2.6. Inserting this into :eq:`eq_FZP_1` gives us the lens radii as follows:

- :math:`r_{1}` = 5.1 mm
- :math:`r_{2}` = 7.46 mm
- :math:`r_{3}` = 9.39 mm
- :math:`r_{4}` = 11.12 mm

:eq:`eq_FZP_2` gives us the step thickness of s = 2.02 mm. Total thickness of the lens is then 4*2.02 = 8.1 mm.

For further details regarding FZP lens design, see [#f1]_.

Lens thickness comparison
-------------------------

For mass production, injection molding is usually cost effective but producing thick lenses can be challenging as sink marks and other deformations can occur. It is therefore of interest to find lens designs which are as thin as possible. In :numref:`fig_lens_thickness_comp` we have compared the lens thickness to diameter ratio (T/D) as a function of :math:`\varepsilon_r`. Common thermoplastics have :math:`\varepsilon_r` in the range 2-4 and the hyperboloidal lens is the thinnest lens. To obtain even thinner lenses, the F/D ratio can be increased; however, this may also increase side lobe levels due to spillover radiation, especially for small-diameter lenses.

Smaller F/D ratios can be chosen than 0.5 with the cost of increased thickness. For short focal distance lenses, the FZP lens is a good options its thickness only depend on :math:`\varepsilon_r`.

.. _fig_lens_thickness_comp:
.. figure:: /_static/handbook/a121/in-depth_topics/integration/lens_thickness_comparison.svg
    :align: center
    :width: 95%

    Lens thickness comparison.

Lens design guidelines and prototyping
======================================

In general, multiple design aspects must be considered when choosing a lens type. Whenever possible, the lens can be made as a part of the outer enclosure and therefore avoid the need for an additional radome. For applications requiring a flat outer surface, convex-planar or FZP lenses are good choices. Outdoor applications may need to consider rain or ice buildup and here the lens outer surface is chosen to minimize this impact. For example, an upwards pointing convex surface would collect less rain.

Manufacturing lenses by injection molding may pose limitations on the lens maximum thickness. For the refracting type lenses, thin lenses are obtained by choosing a high F/D ratio and higher :term:`permittivity<Permittivity>` materials. On the other hand, higher F/D ratios occupy more space as well as increased spillover energy which in turn leads to larger side lobes. For the plano-convex and convex-planar lenses, it is therefore recommended to keep 0.4 < F/D < 0.8. Lens design with F/D outside this range is certainly possible, but with additional loss in directivity and increased side lobes. When large diameter lenses are required, FZP type lenses should be considered as it's thickness only depends on the :term:`permittivity<Permittivity>` and are thus generally thinner than :term:`refracting<Refraction>` type lenses.

For maximum gain and low side-lobe levels, it is important to also follow the PCB ground plane guidelines in :ref:`integration-a121-EM_PCB_groundplane_size`.

Focal distance tuning
---------------------

The focal distance :math:`F` is an input parameter for all lens designs provided here. However, the optimal focal distance may need to be slightly adjusted such that the :term:`reflection<Reflection>` from the lens is simultaneously minimized. In addition, other effects can impact the focal point, such as material :term:`permittivity<Permittivity>` being slightly off, impact of lens housing, radomes and other nearby mechanics.

:numref:`fig_focal_distance_tuning` shows the gain variation of the integrated lens with the radome with respect to the free space scenario for the XM112 module. The maximum gain happens at 7.5 mm distance for both lenses. Other maxima happen every half-a-wavelength (2.5 mm).

.. _fig_focal_distance_tuning:
.. figure:: /_static/handbook/a121/in-depth_topics/integration/gain_vs_focal_distance.png
    :align: center
    :width: 95%

    Gain variation of the lens versus the distance to the XM112 radome. The amplitude is normalized to free space (FS). Gain is stated in one direction (Tx or Rx side). For :term:`RLG` the values will be doubled.

Customized lenses
-----------------

The lens design equations provided here are based on ray optics and may not be adequate in more challenging applications, especially when the lens diameter is small. With a full wave EM solver, Acconeer can construct optimized lenses for maximizing the gain, minimizing the side lobes or customizing the radiation pattern. The impact of lens housings, nearby mechanics and the PCB can also be simulated. Acconeer provides a design service for this, visit the `Acconeer Developer page <a121_lens_design_>`_ for details.


For more information, see:

* :octicon:`download` `A121 Lenses Getting Started Guide <a121_lens_guide_>`_


.. _a121_hw_integration_guideline: https://developer.acconeer.com/download/Hardware-integration-guideline
.. _a121_lens_guide: https://developer.acconeer.com/download/Getting-Started-Guide-A121-Lenses
.. _a121_lens_design: https://developer.acconeer.com/home/design-services/


.. rubric:: Footnotes

.. [#f1]
   J. C. W. D. N. Black, "Millimeter-Wave Characteristics of
   Phase-Correcting Fresnel Zone Plates," *IEEE Transactions on Microwave
   Theory and Techniques*, vol. 35, no. 12, pp. 1122–1129, 1987.
