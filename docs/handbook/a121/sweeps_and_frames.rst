.. _handbook-a121-spf:

Sweeps and frames
=================

The sparse IQ service may be configured to perform several *sweeps* at a time in a so-called *frame*.
Thus, every *frame* received from the sensor consists of a number of *sweeps*.
Every sweep in turn consists of a number of *points* spanning the configured distance *range* (see :ref:`handbook-a121-range`).

Some examples of suitable applications for multiple sweeps per frame are detecting motions, measuring velocities, and tracking objects.

.. _fig_a121_sweep_and_frame_illustration:
.. figure:: /_tikz/res/handbook/a121/sweep_and_frame_illustration.png
   :align: center
   :width: 60%

   An illustration of the *sweep* and *frame* concept.

As shown in :numref:`fig_a121_sweep_and_frame_illustration`,
:math:`N_s` is the number of *sweeps per frame (SPF)*.
Typical values range from 1 to 64.
The sweeps are sampled consecutively, where :math:`T_s` is the time between two corresponding points in consecutive sweeps.
This value is typically specified as the *sweep rate* :math:`f_s=1/T_s`.
It is given by the sensor configuration, but is optionally **limited** to a fixed rate, letting the sensor idle between sweeps.
Typical sweep rates range from 1 kHz to 10 kHz.

In a similar fashion as for sweeps, the *frame rate* is defined as :math:`f_f=1/T_f`.
Typical values range from 1 Hz to 100 Hz.
The sensor may idle in efficient low power states between frames,
so maximizing the idle time between frames is crucial for minimizing the overall power consumption.

.. math::
    :label:

    T_f \geq N_s \cdot T_s
    \Leftrightarrow
    f_f \leq f_s / N_s

The timing of frames can be done in two ways --
either by letting the host trigger measurements of new frames,
or by letting the sensor itself trigger on a periodic timer.

..
    TODO: See :ref:`sec:timing` for a detailed description of the timing in a frame.

Limitations
-----------

As with the number of points :math:`N_d`, the only limitation on the number of sweeps per frame :math:`N_s` itself is related to the available buffer size of 4095 complex numbers.
The buffer usage is the number of points :math:`N_d` times the number of sweeps per frame :math:`N_s`.
In short, :math:`N_d \cdot N_s \leq 4095`.
