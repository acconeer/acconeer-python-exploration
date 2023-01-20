.. _handbook-a121-timing:

Timing
======

.. note::

    The relationships, equations, and constants described here are approximate, not guaranteed, and may change over RSS releases.

Notation
--------

:math:`\tau` -
A time duration.

:math:`f` -
A frequency or rate. Inverse of :math:`T`.

:math:`T` -
A period, the time between recurring events. Inverse of :math:`f`.

:math:`N` -
A number or amount of something.

Overview
--------

.. _fig_a121_intra_frame_timing:
.. figure:: /_tikz/res/handbook/a121/intra_frame_timing.png
   :align: center
   :width: 75%

   Overview for timing within a frame with two sweeps,
   in turn consisting of two subsweeps.
   **Not to scale**, and subsweeps may have different lengths.
   *F→S* and *S→R* are the times required to transition from the configured *inter frame idle state* to the *inter sweep idle state* state, and *inter sweep idle state* to the *ready* state, respectively.
   *FO* and *SO* are the fixed overheads on frame and sweep level with duration :math:`C_f` and :math:`C_s` respectively.
   :math:`S_{i,j}` are subsweeps.

.. _handbook-a121-timing-sample-dur:

Sample duration
---------------

The time to measure a sample :math:`\tau_\text{sample}` is the *added* time per HWAAS for every single measured point.
In most cases, this accounts for the largest part of the sensor measurement time.
The sample duration :math:`\tau_\text{sample}` depends on the configured :ref:`profile <handbook-a121-profiles>` and :class:`PRF <acconeer.exptool.a121.PRF>` according to :numref:`tab_a121_sample_dur` below.

.. _tab_a121_sample_dur:
.. table:: Approximate sample durations :math:`\tau_\text{sample}` for all profile and PRF :math:`f_p` combinations.
    :align: center
    :widths: auto

    +----------------+----------+----------+----------+---------+---------+---------+
    | Profile \\ PRF | 19.5 MHz | 15.6 MHz | 13.0 MHz | 8.7 MHz | 6.5 MHz | 5.2 MHz |
    +================+==========+==========+==========+=========+=========+=========+
    | **1**          |  1539 ns | 1846 ns  | 2154 ns  | 3077 ns | 4000 ns | 4923 ns |
    +----------------+----------+----------+----------+---------+---------+---------+
    | **2**          |     N/A  | 1356 ns  | 1612 ns  | 2382 ns | 3151 ns | 3920 ns |
    +----------------+----------+----------+----------+---------+---------+---------+
    | **3**          |     N/A  | 1026 ns  | 1231 ns  | 1846 ns | 2462 ns | 3077 ns |
    +----------------+----------+----------+----------+---------+---------+---------+
    | **4**          |     N/A  | 1026 ns  | 1231 ns  | 1846 ns | 2462 ns | 3077 ns |
    +----------------+----------+----------+----------+---------+---------+---------+
    | **5**          |     N/A  | 1026 ns  | 1231 ns  | 1846 ns | 2462 ns | 3077 ns |
    +----------------+----------+----------+----------+---------+---------+---------+

Point duration
--------------

The total time it takes to measure a single distance point in a single (sub)sweep is

.. math::
    :label:

    \tau_\text{point} \approx N_a \cdot \tau_\text{sample} + \tau_\text{point overhead}

where
:math:`N_a` is the configured HWAAS (number of averages),
and
:math:`\tau_\text{point overhead}` is given by :numref:`tab_a121_point_overhead` below.

.. _tab_a121_point_overhead:
.. table:: Approximate durations of the point overhead :math:`\tau_\text{point overhead}` for all profile and PRF :math:`f_p` combinations.
    :align: center
    :widths: auto

    +----------------+----------+----------+----------+---------+---------+---------+
    | Profile \\ PRF | 19.5 MHz | 15.6 MHz | 13.0 MHz | 8.7 MHz | 6.5 MHz | 5.2 MHz |
    +================+==========+==========+==========+=========+=========+=========+
    | **1**          |  1744 ns | 2102 ns  | 2462 ns  | 3539 ns | 4615 ns | 5692 ns |
    +----------------+----------+----------+----------+---------+---------+---------+
    | **2**          |     N/A  | 1612 ns  | 1920 ns  | 2844 ns | 3766 ns | 4689 ns |
    +----------------+----------+----------+----------+---------+---------+---------+
    | **3**          |     N/A  | 1282 ns  | 1539 ns  | 2308 ns | 3077 ns | 3846 ns |
    +----------------+----------+----------+----------+---------+---------+---------+
    | **4**          |     N/A  | 1282 ns  | 1539 ns  | 2308 ns | 3077 ns | 3846 ns |
    +----------------+----------+----------+----------+---------+---------+---------+
    | **5**          |     N/A  | 1282 ns  | 1539 ns  | 2308 ns | 3077 ns | 3846 ns |
    +----------------+----------+----------+----------+---------+---------+---------+

Subsweep duration
-----------------

The total time it takes to measure a single subsweep,
including the time it takes to initialize the measurement is

.. math::
    :label:

    \tau_\text{subsweep} \approx N_d \cdot \tau_\text{point} + \underbrace{3 \cdot \tau_\text{sample} + C_\text{subsweep}}_\text{overhead}

where
:math:`N_d` is the configured number of distances (``num_points``),
and
:math:`C_\text{subsweep} \approx 26 \mu\text{s}` is a fixed overhead.

..
    Fix μ

Sweep duration
--------------

The time to measure a sweep :math:`\tau_s` is the total time it takes to measure a single sweep,
including all configured subsweeps and transitioning from the configured inter sweep idle state.

.. math::
    :label:

    \tau_s \approx \tau_{S \rightarrow R} + \sum (\tau_\text{subsweep}) + C_s

where
:math:`\tau_{S \rightarrow R}` is the *sweep transition time*,
and
:math:`C_s \approx 10 \mu\text{s}` is a fixed overhead.

The sweep transition time :math:`\tau_{S \rightarrow R}` is the time required to transition from the configured *inter sweep idle state* to the *ready* state.
See :numref:`tab_a121_transition_times` below.

Idle state transition times
^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. _tab_a121_transition_times:
.. table:: Approximate transition times between the idle states.
    :align: center
    :widths: auto

    +----------------+------------+---------+---------+
    | From \\ To     | Deep sleep |   Sleep |   Ready |
    +================+============+=========+=========+
    | **Deep sleep** |       0 us |  585 us |  650 us |
    +----------------+------------+---------+---------+
    | **Sleep**      |        N/A |    0 us |   65 us |
    +----------------+------------+---------+---------+
    | **Ready**      |        N/A |     N/A |    0 us |
    +----------------+------------+---------+---------+

Sweep period
------------

The sweep period :math:`T_s` is the time between the start of two consecutive sweeps in a frame.

If the *sweep rate* is not set, the sweep period will be equal to the sweep duration;
:math:`T_s = \tau_s`.

If the *sweep rate* is set, the sensor will idle in the configured *inter sweep idle state* between sweeps.
This idle time is called the *inter sweep idle time*, :math:`\tau_{si}`.

.. math::
    :label:

    T_s = \frac{1}{f_s} = \tau_s + \tau_{si}

Frame duration
--------------

The time to measure a frame :math:`\tau_f` is the total time it takes to measure a frame,
including all sweeps and transitioning from the configured inter frame idle state.

.. math::
    :label:

    \tau_f \approx \tau_{F \rightarrow S} + (N_s - 1) \cdot T_s + \tau_s + C_f

where
:math:`\tau_{F \rightarrow S}` is the *frame transition time*,
:math:`N_s` is the SPF (sweeps per frame),
and
:math:`C_f \approx 4 \mu\text{s}` is a fixed overhead.

The frame transition time :math:`\tau_{F \rightarrow S}` is the time required to transition from the configured *inter frame idle state* to the *inter sweep idle state* state.
See :numref:`tab_a121_transition_times` above.

Frame period
------------

The frame period :math:`T_f` is the time between the start of two consecutive frames.
The sensor will idle in the configured *inter frame idle state* between frames.
This idle time is called the *inter frame idle time*, :math:`\tau_{fi}`.

.. math::
    :label: eq_a121_frame_period

    T_f = \frac{1}{f_f} = \tau_f + \tau_{fi}

In most cases, the sensor will not measure (again) until the host commands it to.
This means that the frame period, and thus also the *inter frame idle time*, is given by how the host controls the sensor.

If the *frame rate* is not set,
the sensor will measure immediately once the host commands it to.
Thus, the frame period will be larger than the frame duration;
:math:`T_f > \tau_f`.

If the *frame rate* :math:`f_f` is set, the sensor will continue to idle until :eq:`eq_a121_frame_period` is met.
