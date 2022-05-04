Radar principles
================

Reflectivity
------------

The amount of energy received back to the Rx antenna depends on the reflectivity of the object (:math:`\gamma`), the radar cross section (RCS) of the object (:math:`\sigma`), and the distance to the object (:math:`R`).
A reflection occurs when there is a difference in relative permittivity between two media that the signal is propagating through.
:math:`\gamma` is then given as

.. math::
    :label: eq_reflectivity

    \gamma=\left(\frac{\sqrt{\varepsilon_1}-\sqrt{\varepsilon_2}}{\sqrt{\varepsilon_1}+\sqrt{\varepsilon_2}}\right)^2

where :math:`\varepsilon_1` and :math:`\varepsilon_2` is the relative permittivity, at 60 GHz, on either side of the boundary.
The relative permittivity for common materials can be found in various data bases, but keep in mind that it is frequency dependent.
As an example, :numref:`tab_material` lists approximate values for the real part of the relative permittivity for some common materials.

.. _tab_material:
.. table:: Relative permittivity of common materials
    :align: center
    :widths: auto

    ==================== ===================================== ===========================================
    Material             Real(:math:`\varepsilon`) at 60 GHz   :math:`\gamma` with air boundary
    ==================== ===================================== ===========================================
    ABS plastic          2.48                                  0.049
    Mobile phone glass   6.9                                   0.02
    Plaster              2.7                                   0.059
    Concrete             4                                     0.11
    Wood                 2.4                                   0.046
    Textile              2                                     0.029
    Metal                --                                    1
    Human skin           8                                     0.22
    Water                11.1                                  0.28
    Air                  1                                     0
    ==================== ===================================== ===========================================


:numref:`tab_material` shows that some materials are semi-transparent to 60 GHz signals and it is hence possible to detect reflecting objects behind a surface of these materials, each boundary with a change in permittivity gives a reflection.
This is a useful property in applications where the use case requires that the sensor measures through, e.g., a wall, clothing or plastic housing.

Radar cross section
-------------------

The radar cross section is the effective area of the object that the signal is reflected against, for simple geometrical shapes, where the size is larger than the wavelength of the signal (~5 mm) and is in the far-field distance, it can be expressed analytically as in :numref:`fig_rcs`.
The far-field distance depends on the object size and its distance to the radar source.
Generally speaking, far-field applies when the waves reflected by the object can be considered plane-waves.
Representative back scattering pattern of a sphere, flat plate and trihedral corner reflector are shown in the polar plots.
It is seen that the objects can have different maximum RCS, but also different radiation patterns, a flat plate for instance is very directive and if tilted away from the radar, the received energy will be decreased, whereas the corner has less angular dependence and is a more robust reflector in terms of angle with respect to the radar.

.. _fig_rcs:
.. figure:: /_static/introduction/fig_rcs.png
    :align: center
    :width: 95%

    Radiation pattern and analytical expressions for simple geometrical shapes.

For most objects it is not possible to analytically calculate :math:`\sigma`, instead it needs to be measured or modelled.
