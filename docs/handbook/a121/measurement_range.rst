.. _handbook-a121-range:

Measurement range
=================

The sparse IQ service can be configured to measure practically any range of distances in a so-called *sweep*.
In other words, a sweep makes up the points in space where reflected pulses are measured.

.. _fig_a121_data_simple:
.. figure:: /_static/handbook/a121/data_simple.png
   :align: center
   :width: 80%

   Amplitude of a mocked sweep of an environment with a single object.

:numref:`fig_a121_data_simple` above shows an example of a sweep with a range spanning from a start point at ~ 0.50 m to an end point at ~ 0.81 m.
Here, a total of 32 points were measured with a distance between them of ~ 10 mm, also configurable.
The shortest configurable distance between points is ~ 2.5 mm.

The more points that are measured, the more memory is used and the longer it takes to measure the sweep.
This may in turn lead to higher overall duty cycle and power consumption.
Thus, it is often important to try to minimize the number of points measured,
typically achieved by maximizing the distance between the points.

Configuration
-------------

For preciseness, the range is configured in a discrete scale with three integer parameters --
the *start point* :math:`d_1`,
the *number of points* :math:`N_d`, and
the *step length* :math:`\Delta d`.
The *step length* corresponds to the distance between the points (mentioned above).
The distance between the points in the discrete scale is ~ 2.5 mm,
which is also why the shortest configurable distance between points is just that.

.. _fig_a121_range_illustration:
.. figure:: /_tikz/res/handbook/a121/range_illustration.png
   :align: center
   :width: 60%

   An illustration of the sweep *range* concept.

:numref:`fig_a121_range_illustration` above demonstrates how a range can be set up with these parameters.
The start point :math:`d_1=20`, the number of points :math:`N_d=4`, and the step length :math:`\Delta d = 3`
This gives the discrete points
:math:`\{20, 23, 26, 29\}`
which correspond to
:math:`\{50.0 mm, 57.5 mm, 65.0 mm, 72.5 mm\}`.

Note that the possible values for step length :math:`\Delta d` are limited.

Limitations
-----------

The only limitation on the number of points :math:`N_d` itself is related to the available buffer size of 4095 complex numbers.
The buffer usage is the number of points :math:`N_d` times the number of sweeps per frame :math:`N_s`
(see :ref:`handbook-a121-spf`).
In short, :math:`N_d \cdot N_s \leq 4095`.

The step length must be a divisor or multiple of 24.
The shortest step length, 1, gives a distance between points of ~ 2.5 mm.
See :numref:`tab_a121_steplen` for an overview.

.. _tab_a121_steplen:
.. table:: Overview of selectable step lengths.
    :align: center
    :widths: auto

    +--------------------------+----------+--------------------------+----------+
    | Step length                         | Step length cont'd                  |
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

See :ref:`handbook-a121-spf` on the PRF for more details.

Caveats
-------

A number of factors affect the actual real world distance of a given range point:

- The refractive index and thickness of materials the radar signal pass through.
- Systematic errors due to process, supply voltage, and temperature variations.
- Reference clock frequency.

Some static offsets can be compensated for by doing a *loopback* measurement of the "zero point".
