.. _rdac-a121-timing:

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

.. _rdac-a121-timing-sample-dur:

Sample duration
---------------

The time to measure a sample :math:`\tau_\text{sample}` is the *added* time per HWAAS for every single measured point.
In most cases, this accounts for the largest part of the sensor measurement time.
The sample duration :math:`\tau_\text{sample}` depends on the configured :ref:`profile <rdac-a121-profiles>` and :class:`PRF <acconeer.exptool.a121.PRF>` according to :numref:`tab_a121_sample_dur` below.

.. _tab_a121_sample_dur:
.. table:: Approximate sample durations :math:`\tau_\text{sample}` for all profile and PRF :math:`f_p` combinations.
    :align: center
    :widths: auto

    +----------------+----------+----------+----------+---------+---------+---------+
    | Profile \\ PRF | 19.5 MHz | 15.6 MHz | 13.0 MHz | 8.7 MHz | 6.5 MHz | 5.2 MHz |
    +================+==========+==========+==========+=========+=========+=========+
    | **1**          |  1487 ns | 1795 ns  | 2103 ns  | 3026 ns | 3949 ns | 4872 ns |
    +----------------+----------+----------+----------+---------+---------+---------+
    | **2**          |     N/A  | 1344 ns  | 1600 ns  | 2369 ns | 3138 ns | 3908 ns |
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
:math:`C_\text{subsweep}` is a fixed overhead, see section :ref:`sec_fixed_overheads_and_hsm`.

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
:math:`C_s` is a fixed overhead, see section :ref:`sec_fixed_overheads_and_hsm`.

The sweep transition time :math:`\tau_{S \rightarrow R}` is the time required to transition from the configured *inter sweep idle state* to the *ready* state.
See :numref:`tab_a121_transition_times` below.

Idle state transition times
^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. _tab_a121_transition_times:
.. table:: Approximate transition times between the idle states.
    :align: center
    :widths: auto

    +----------------+-----------------------+-------------------------+-------------------------+
    | From \\ To     | Deep sleep            |                   Sleep |                   Ready |
    +================+=======================+=========================+=========================+
    | **Deep sleep** | :math:`0 \mu\text{s}` | :math:`615 \mu\text{s}` | :math:`670 \mu\text{s}` |
    +----------------+-----------------------+-------------------------+-------------------------+
    | **Sleep**      |                   N/A |   :math:`0 \mu\text{s}` |  :math:`55 \mu\text{s}` |
    +----------------+-----------------------+-------------------------+-------------------------+
    | **Ready**      |                   N/A |                     N/A |   :math:`0 \mu\text{s}` |
    +----------------+-----------------------+-------------------------+-------------------------+

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
:math:`C_f` is a fixed overhead, see section :ref:`sec_fixed_overheads_and_hsm`.

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

.. _sec_fixed_overheads_and_hsm:

Fixed overheads and high speed mode (HSM)
-----------------------------------------

The fixed overheads for subsweep, :math:`C_\text{subsweep}`, sweep, :math:`C_s`, and frame, :math:`C_f`, are dependent on if high speed mode is activated or not.
High speed mode means that the sensor is configured in a way where it can optimize its measurements to obtain as high sweep rate as possible.
In order for the sensor to operate in high speed mode, the following configuration constraints apply:

- :attr:`~acconeer.exptool.a121.SensorConfig.continuous_sweep_mode`: False
- :attr:`~acconeer.exptool.a121.SensorConfig.inter_sweep_idle_state`: READY
- :attr:`~acconeer.exptool.a121.SensorConfig.num_subsweeps`: 1
- :attr:`~acconeer.exptool.a121.SubsweepConfig.profile`: 3-5

Note that the default RSS Service configuration comply with these constraints which means that high speed mode is activated by default.

The fixed overheads can be seen in :numref:`tab_a121_fixed_overheads` below.

.. _tab_a121_fixed_overheads:
.. table:: Approximate fixed overhead times.
    :align: center
    :widths: auto

    +------------------+---------------------------+------------------------+-----------------------+
    | Mode \\ Overhead | :math:`C_\text{subsweep}` | :math:`C_s`            | :math:`C_f`           |
    +==================+===========================+========================+=======================+
    | Normal           |    :math:`22 \mu\text{s}` | :math:`10 \mu\text{s}` | :math:`4 \mu\text{s}` |
    +------------------+---------------------------+------------------------+-----------------------+
    | High speed       |     :math:`0 \mu\text{s}` |  :math:`0 \mu\text{s}` | :math:`36 \mu\text{s}`|
    +------------------+---------------------------+------------------------+-----------------------+
