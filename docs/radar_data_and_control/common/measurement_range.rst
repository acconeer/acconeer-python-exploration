Measurement range
=================

Sweep range
-----------

The sparse IQ service can be configured to measure practically any range of distances in a so-called *sweep*.
In other words, a sweep makes up the points in space where reflected pulses are measured.

.. _fig_data_simple_SENSOR_PLACEHOLDER_LOWER:
.. figure:: /images/handbook/a121/data_simple.png
   :align: center
   :width: 80%

   Amplitude of a mocked sweep of an environment with a single object.

:numref:`fig_data_simple_SENSOR_PLACEHOLDER_LOWER` above shows an example of a sweep with a range spanning from a start point at ~ 0.50 m to an end point at ~ 0.81 m.
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

.. _fig_range_illustration_SENSOR_PLACEHOLDER_LOWER:
.. figure:: /_tikz/res/handbook/a121/range_illustration.png
   :align: center
   :width: 60%

   An illustration of the sweep *range* concept.

:numref:`fig_range_illustration_SENSOR_PLACEHOLDER_LOWER` above demonstrates how a range can be set up with these parameters.
The start point :math:`d_1=20`, the number of points :math:`N_d=4`, and the step length :math:`\Delta d = 3`
This gives the discrete points
:math:`\{20, 23, 26, 29\}`
which correspond to
:math:`\{50.0 mm, 57.5 mm, 65.0 mm, 72.5 mm\}`.

Note that the possible values for step length :math:`\Delta d` are limited.

Caveats
-------

A number of factors affect the actual real world distance of a given range point:

- The refractive index and thickness of materials the radar signal pass through.
- Systematic errors due to process, supply voltage, and temperature variations.
- Reference clock frequency.
