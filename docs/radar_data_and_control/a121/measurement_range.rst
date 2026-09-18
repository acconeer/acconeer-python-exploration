.. _rdac-a121-measurement-range:

.. include:: ../common/measurement_range.rst

Limitations
-----------

The only limitation on the number of points :math:`N_d` itself is related to the available buffer size of 4095 complex numbers.
The buffer usage is the number of points :math:`N_d` times the number of sweeps per frame :math:`N_s`
(see :ref:`rdac-a121-sweeps-and-frames`).
In short, :math:`N_d \cdot N_s \leq 4095`.

The step length must be a divisor or multiple of 24.
The shortest step length, 1, gives a distance between points of ~ 2.5 mm.
See :numref:`tab_a121_steplen` for an overview.

.. _tab_a121_steplen:
.. table:: Overview of selectable step lengths.
    :align: center
    :widths: auto

    +--------------------------+----------+--------------------------+----------+
    | Step length                         | Step length continued               |
    +--------------------------+----------+--------------------------+----------+
    | Setting :math:`\Delta d` | Distance | Setting :math:`\Delta d` | Distance |
    +==========================+==========+==========================+==========+
    |  1                       |  2.5 mm  |                       24 |  60 mm   |
    +--------------------------+----------+--------------------------+----------+
    |  2                       |  5.0 mm  |                       48 | 120 mm   |
    +--------------------------+----------+--------------------------+----------+
    |  3                       |  7.5 mm  |                       72 | 180 mm   |
    +--------------------------+----------+--------------------------+----------+
    |  4                       | 10.0 mm  |                       96 | 240 mm   |
    +--------------------------+----------+--------------------------+----------+
    |  6                       | 15.0 mm  |                      120 | 300 mm   |
    +--------------------------+----------+--------------------------+----------+
    |  8                       | 20.0 mm  |                      144 | 360 mm   |
    +--------------------------+----------+--------------------------+----------+
    | 12                       | 30.0 mm  |                      ... | ...      |
    +--------------------------+----------+--------------------------+----------+


The *maximum measurable distance (MMD)*, i.e., the farthest configurable "end point",
is limited by the
*pulse repetition frequency (PRF)*.
The lower PRF, the longer MMD.

The PRF also gives the
*maximum unambiguous range (MUR)*
--
the maximum range at which target can be located at while still guaranteeing that the reflected pulse corresponds to the most recent transmitted pulse.
Again, the lower PRF, the longer MUR.

See :ref:`rdac-a121-sweeps-and-frames` on the PRF for more details.

Some static offsets can be compensated for by doing a *loopback* measurement of the "zero point".
