################
Radar Principles
################

Introduction
------------

The strength of the signal received back at the Rx antenna depends on
three key parameters: the reflectivity (:math:`\gamma`) of the material
boundaries the signal passes through, the radar cross section
(:math:`\sigma`) of the target object, and the distance (:math:`R`) to the
object.

Understanding these parameters is useful when working out how the sensor
will behave in a given application.
The reflectivity determines how much energy is reflected at each material
boundary.
The RCS characterizes how effectively a target scatters energy back toward
the sensor, and depends on both the size and shape of the object.
The distance influences the received power through path loss: signal energy
spreads out over a larger area as it travels further, reducing the received
amplitude.

Each of these parameters is discussed in the sections below.

Reflectivity
------------

A reflection occurs when there is a difference in relative permittivity
between two media that the signal is propagating through.
The reflectivity :math:`\gamma` characterizes the fraction of energy
reflected at a material boundary and is given as

.. math::
    :label: eq_reflectivity

    \gamma=\left(\frac{\sqrt{\varepsilon_1}-\sqrt{\varepsilon_2}}{\sqrt{\varepsilon_1}+\sqrt{\varepsilon_2}}\right)^2

where :math:`\varepsilon_1` and :math:`\varepsilon_2` are the relative
permittivity on either side of the boundary.
:numref:`tab_material` lists approximate values for the real part of the
relative permittivity for some common materials.

.. _tab_material:
.. table:: Approximate relative permittivity of common materials
    :align: center
    :widths: auto

    =============================== ===================================== =====================================
    Material                        Re(:math:`\varepsilon`) at 60 GHz     :math:`\gamma` with air boundary
    =============================== ===================================== =====================================
    Air                             1                                     0
    ABS                             2.5-4.0                               0.05 - 0.11
    Polyethylene (PE)               2.3                                   0.042
    Polypropylene (PP)              2.2                                   0.038
    Polycarbonate                   2.75                                  0.06
    Mobile phone glass              6.9                                   0.2
    Plaster                         2.7                                   0.059
    Concrete                        4                                     0.11
    Wood                            2.4                                   0.046
    Textile                         2                                     0.029
    Metal                           --                                    1
    Human skin                      8                                     0.22
    Water                           11.1                                  0.28
    =============================== ===================================== =====================================


:numref:`tab_material` shows that some materials are semi-transparent to
60 GHz signals and it is hence possible to detect reflecting objects behind
a surface of these materials, each boundary with a change in permittivity
gives a reflection.
This is a useful property in applications where the sensor measures through
the product housing or when detecting objects behind other objects such as
walls and clothing. For optimal design of the product housing,
see :ref:`integration-a121-radomes`.

Radar Cross Section
-------------------

The radar cross section is the effective area of the object that the signal
is reflected against.
Far-field conditions apply when the waves reflected by the object can be
considered plane-waves, which generally holds when the object is sufficiently
far from the radar relative to its size.
For simple geometrical shapes larger than the wavelength (~5 mm) in the far
field, the RCS can be expressed analytically as shown in :numref:`fig_rcs`.
Representative back scattering pattern of a sphere, flat plate and trihedral
corner reflector are shown in the polar plots.
It is seen that the objects can have different maximum RCS, but also
different radiation patterns, a flat plate for instance is very directive
and if tilted away from the radar, the received energy will be decreased,
whereas the corner has less angular dependence and is a more robust reflector
in terms of angle with respect to the radar.

.. _fig_rcs:
.. figure:: /images/introduction/fig_rcs.png
    :align: center
    :width: 95%

    Radiation pattern and analytical expressions for simple geometrical
    shapes.

For most real-world objects it is not possible to analytically calculate
:math:`\sigma`; instead it needs to be measured or modeled. Understanding
the expected RCS of a target is therefore an important part of characterizing
sensor performance in any specific application.

Distance
--------

The distance :math:`R` to the object affects the strength of the received
signal through free-space path loss. As the signal travels from the sensor
to the object and back, it spreads out over an increasingly large area,
reducing the power density. Since the signal makes a round trip, the
received power scales with :math:`R^{-4}`, meaning that doubling the
distance reduces the received power by a factor of 16.

