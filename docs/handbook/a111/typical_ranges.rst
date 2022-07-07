Typical ranges for different objects
====================================

In :numref:`tab_range_wo_lens` and :numref:`tab_range_w_lens` the visibility for a range of objects with common shapes (cylinder, plate, etc.) and of varying reflectivity, i.e. materials, is shown. Objects are at normal incidence and the governing system parameters are :math:`\sigma`, :math:`\gamma`, and C, as shown in :eq:`eq_radar_eq`. The envelope service was used to collect the data with Profile 2. The object counts as distinguishable from the noise with a SNR > 10 dB (Y), barely visible between 5 dB and 10 dB (-) and not visible with a SNR < 5 dB (N).
The range can be further increased based on the configuration of the sensor, as described in :ref:`handbook-a111-configuring` and by optimizing the physical integration, as will be described in :ref:`handbook-physical-integration`. As an example for such an optimization :numref:`tab_range_wo_lens` shows results with an added radar Fresnel lens.

.. _tab_range_wo_lens:
.. table:: Typical ranges using the envelope service and Profile 2, **without radar lens**.
    :align: center
    :widths: auto

    =============================================== ===== ===== ===== ===== =====
    Object                                          0.5 m 1 m   2 m   5 m   7 m
    =============================================== ===== ===== ===== ===== =====
    Corner reflector (*a* = 4 cm)                   Y     Y     Y     Y     N
    Planar water surface                            Y     Y     Y     Y     Y
    Disc (*r* = 4 cm)                               Y     Y     Y     Y     Y
    Cu Plate (10x10 cm)                             Y     Y     Y     Y     Y
    PET plastic Plate (10x10 cm)                    Y     Y     Y     Y     --
    Wood Plate (10x10 cm)                           Y     Y     --    N     N
    Cardboard Plate (10x10 cm)                      Y     Y     Y     N     N
    Al Cylinder (*h* = 30, *r* = 2 cm)              Y     Y     --    N     N
    Cu Cylinder (*h* = 12, *r* = 1.6 cm)            Y     Y     Y     N     N
    PP plastic Cylinder (*h* = 12, *r* = 1.6 cm)    Y     N     N     N     N
    Leg                                             Y     Y     --    N     N
    Hand (front)                                    Y     Y     N     N     N
    Torso (front)                                   Y     Y     Y     N     N
    Head                                            Y     Y     N     N     N
    Glass with water (*h* = 8.5, *r* = 2.7 cm)      Y     Y     N     N     N
    PET Bottle with water (*h* = 14, *r* = 4.2 cm)  Y     Y     N     N     N
    Football                                        Y     Y     N     N     N
    =============================================== ===== ===== ===== ===== =====

.. _tab_range_w_lens:
.. table:: Typical ranges using the envelope service and Profile 2, **with 7 dB radar lens**.
    :align: center
    :widths: auto

    ============================================== ===== ===== ===== ===== =====
    Object                                         0.5 m 1 m   2 m   5 m   7 m
    ============================================== ===== ===== ===== ===== =====
    Corner reflector (*a* = 4 cm)                  Y     Y     Y     Y     Y
    Planar water surface                           Y     Y     Y     Y     Y
    Disc (*r* = 4 cm)                              Y     Y     Y     Y     Y
    Cu Plate (10x10 cm)                            Y     Y     Y     Y     Y
    PET plastic Plate (10x10 cm)                   Y     Y     Y     Y     Y
    Wood Plate (10x10 cm)                          Y     Y     Y     Y     N
    Cardboard Plate (10x10 cm)                     Y     Y     Y     Y     --
    Al Cylinder (*h* = 30, *r* = 2 cm)             Y     Y     Y     Y     --
    Cu Cylinder (*h* = 12, *r* = 1.6 cm)           Y     Y     Y     Y     --
    PP plastic Cylinder (*h* = 12, *r* = 1.6 cm)   Y     Y     Y     N     N
    Leg                                            Y     Y     Y     Y     N
    Hand (front)                                   Y     Y     Y     N     N
    Torso (front)                                  Y     Y     Y     Y     N
    Head                                           Y     Y     Y     --    N
    Glass with water (*h* = 8.5, *r* = 2.7 cm)     Y     Y     Y     --    N
    PET Bottle with water (*h* = 14, *r* = 4.2 cm) Y     Y     Y     N     N
    Football                                       Y     Y     Y     N     N
    ============================================== ===== ===== ===== ===== =====
