.. _rdac-a212-measurement-range:

.. include:: ../common/measurement_range.rst

Step length
-----------

The base distance between measurement points is approximately 2.5 mm when step length :math:`\Delta d = 1`.
The step length can be set to any integer from 1 to 3072, giving a maximum inter-point spacing of
approximately 7.7 m. In practice, step lengths rarely exceed a few hundred, as larger spacings
would cause most targets to fall between measurement points.

Pulse repetition frequency
--------------------------

The *maximum measurable distance (MMD)*, i.e., the farthest configurable end point,
and the *maximum unambiguous range (MUR)* depend on the *pulse repetition frequency (PRF)*.
The lower the PRF, the longer the MMD and MUR, as listed in :numref:`tab_a212_prf`.

.. _tab_a212_prf:
.. table:: PRF settings with corresponding MMD and MUR for A212.
    :align: center
    :widths: auto

    +------------------+----------+--------+--------+
    | PRF setting      | PRF      | MMD    | MUR    |
    +==================+==========+========+========+
    | ``PRF_27_7_MHZ`` | 27.7 MHz |  2.4 m |  5.4 m |
    +------------------+----------+--------+--------+
    | ``PRF_20_8_MHZ`` | 20.8 MHz |  4.2 m |  7.2 m |
    +------------------+----------+--------+--------+
    | ``PRF_15_8_MHZ`` | 15.8 MHz |  6.6 m |  9.6 m |
    +------------------+----------+--------+--------+
    | ``PRF_12_5_MHZ`` | 12.5 MHz |  9.0 m | 12.0 m |
    +------------------+----------+--------+--------+
    | ``PRF_8_3_MHZ``  |  8.3 MHz | 15.0 m | 18.0 m |
    +------------------+----------+--------+--------+
    | ``PRF_5_3_MHZ``  |  5.3 MHz | 25.0 m | 28.0 m |
    +------------------+----------+--------+--------+

The default PRF is ``PRF_20_8_MHZ``, giving an MMD of 4.2 m.

Objects located beyond the MUR may fold back into the measured range.
For example, with ``PRF_20_8_MHZ`` (MUR 7.2 m), an object at 8.0 m could appear at
:math:`8.0 - 7.2 = 0.8` m.

.. seealso::

   :py:class:`~acconeer.exptool.a2.PRF` for the complete enumeration of PRF values.
