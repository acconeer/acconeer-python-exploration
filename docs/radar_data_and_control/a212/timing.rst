.. _rdac-a212-timing:

Timing
======

.. note::

    The relationships, equations, and constants described here are approximate, not guaranteed, and may change over RSS releases.

.. seealso::

    The :doc:`/resource_calc` in the Exploration Tool estimates timing and power consumption
    for a given configuration.

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

Sample duration
---------------

The time to measure one sample :math:`\tau_\text{sample}` depends on the configured
:class:`Profile <acconeer.exptool.a2.Profile>` and :class:`PRF <acconeer.exptool.a2.PRF>`
according to :numref:`tab_a212_sample_dur` below.

.. _tab_a212_sample_dur:
.. table:: Approximate sample durations :math:`\tau_\text{sample}` for all profile and PRF :math:`f_p` combinations.
    :align: center
    :widths: auto

    +----------------+----------+----------+----------+----------+
    | Profile \\ PRF | 27.7 MHz | 20.8 MHz | 8.3 MHz  | 5.3 MHz  |
    +================+==========+==========+==========+==========+
    | **1**          | 4.84 µs  | 6.09 µs  | 13.59 µs | 20.54 µs |
    +----------------+----------+----------+----------+----------+
    | **2**          | 4.26 µs  | 5.32 µs  | 11.66 µs | 17.55 µs |
    +----------------+----------+----------+----------+----------+
    | **3**          | 3.40 µs  | 4.16 µs  | 8.78 µs  | 13.06 µs |
    +----------------+----------+----------+----------+----------+
    | **4**          | 2.82 µs  | 3.40 µs  | 6.86 µs  | 10.07 µs |
    +----------------+----------+----------+----------+----------+
    | **5**          | 2.24 µs  | 2.62 µs  | 4.93 µs  | 7.07 µs  |
    +----------------+----------+----------+----------+----------+
    | **6**          | 2.24 µs  | 2.62 µs  | 4.93 µs  | 7.07 µs  |
    +----------------+----------+----------+----------+----------+

Subsweep duration
-----------------

The time to measure a single subsweep is

.. math::
    :label:

    \tau_\text{subsweep} \approx C_\text{subsweep} + N_{a,\text{total}} \cdot N_\text{TX} \cdot \tau_\text{sample}

where
:math:`N_{a,\text{total}} = \sum_d \text{HWAAS}(d)` is the sum of HWAAS values over all distance
points in the subsweep (see :ref:`rdac-a212-signal-strength` for HWAAS scaling),
:math:`N_\text{TX}` is the number of active TX antennas,
and :math:`C_\text{subsweep}` is a fixed overhead (see :numref:`tab_a212_fixed_overheads`).

For constant HWAAS (HWAAS exponent :math:`e = 0`): :math:`N_{a,\text{total}} = N_d \cdot N_a`,
where :math:`N_d` is ``num_points`` and :math:`N_a` is ``hwaas_max``.

Sweep duration
--------------

The time to measure a sweep :math:`\tau_s` includes all configured subsweeps and the transition
from the configured :attr:`~acconeer.exptool.a2.SensorConfig.inter_sweep_idle_state`.

.. math::
    :label:

    \tau_s \approx \tau_{S \rightarrow R} + \sum_i \tau_{\text{subsweep},i}

where :math:`\tau_{S \rightarrow R}` is the sweep transition time from the configured idle state
(see :numref:`tab_a212_transition_times`).

Idle state transition times
^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. _tab_a212_transition_times:
.. table:: Approximate sweep transition times :math:`\tau_{S \rightarrow R}` per idle state.
    :align: center
    :widths: auto

    +------------+--------------------------------+
    | Idle state | :math:`\tau_{S \rightarrow R}` |
    +============+================================+
    | ARMED      | :math:`1.82 \mu\text{s}`       |
    +------------+--------------------------------+
    | READY      | :math:`92.8 \mu\text{s}`       |
    +------------+--------------------------------+

Sweep period
------------

The sweep period :math:`T_s` is the time between the start of two consecutive sweeps in a frame.

If the :attr:`~acconeer.exptool.a2.SensorConfig.sweep_rate` is not set, the sweep period equals
the sweep duration: :math:`T_s = \tau_s`.

If the sweep rate :math:`f_s` is set, the sensor idles in the configured
:attr:`~acconeer.exptool.a2.SensorConfig.inter_sweep_idle_state` between sweeps.

.. math::
    :label:

    T_s = \frac{1}{f_s} = \tau_s + \tau_{si}

where :math:`\tau_{si}` is the inter-sweep idle time.

Frame duration
--------------

The time to measure a frame :math:`\tau_f` includes all sweeps and the fixed frame overhead.

.. math::
    :label:

    \tau_f \approx N_s \cdot T_s + C_f

where :math:`N_s` is the sweeps per frame and :math:`C_f` is a fixed overhead
(see :numref:`tab_a212_fixed_overheads`).

.. note::

   This formula assumes
   :attr:`~acconeer.exptool.a2.SensorConfig.inter_frame_idle_state` equals
   :attr:`~acconeer.exptool.a2.SensorConfig.inter_sweep_idle_state`, which is the default.
   If they differ, the first sweep in each frame transitions from the
   inter-frame idle state and may take longer than subsequent sweeps.

Frame period
------------

The frame period :math:`T_f` is the time between the start of two consecutive frames.
Between frames, the sensor idles in the configured
:attr:`~acconeer.exptool.a2.SensorConfig.inter_frame_idle_state`.

If the :attr:`~acconeer.exptool.a2.SensorConfig.frame_rate` is not set, the sensor measures as
soon as the host commands it to, so in practice :math:`T_f > \tau_f` because of host readout and
command overhead.

If the frame rate :math:`f_f` is set, the sensor idles until the configured period is reached:

.. math::
    :label: eq_a212_frame_period

    T_f = \frac{1}{f_f} = \tau_f + \tau_{fi}

where :math:`\tau_{fi}` is the inter-frame idle time. The frame period, and thus also the
inter-frame idle time, is given by how the host controls the sensor.

.. _sec_a212_fixed_overheads:

Fixed overheads and high speed mode
------------------------------------

The fixed overheads for subsweep (:math:`C_\text{subsweep}`) and frame (:math:`C_f`) depend on
whether high speed mode (HSM) is active.

HSM is activated when all of the following conditions are met:

- :attr:`~acconeer.exptool.a2.SensorConfig.num_subsweeps`: 1
- :attr:`~acconeer.exptool.a2.SensorConfig.sweeps_per_frame`: > 1
- :attr:`~acconeer.exptool.a2.SensorConfig.jitter_compensation`: False

In HSM there is no separate sweep transition time :math:`\tau_{S \rightarrow R}`; instead, the
idle-state-dependent transition cost is included in the subsweep overhead
:math:`C_\text{subsweep}`. The sweep duration formula therefore reduces to
:math:`\tau_s \approx \tau_\text{subsweep}`.

.. _tab_a212_fixed_overheads:
.. table:: Approximate fixed overhead times.
    :align: center
    :widths: auto

    +----------------------------+--------------------------------------+-----------------------+
    | Mode                       | :math:`C_\text{subsweep}`            | :math:`C_f`           |
    +============================+======================================+=======================+
    | Normal (HSM not active)    | :math:`32.6 \mu\text{s}`             | :math:`4 \mu\text{s}` |
    +----------------------------+--------------------------------------+-----------------------+
    | HSM (ARMED)                | :math:`20.4 \mu\text{s}`             | :math:`4 \mu\text{s}` |
    +----------------------------+--------------------------------------+-----------------------+
    | HSM (READY)                | :math:`112.5 \mu\text{s}`            | :math:`4 \mu\text{s}` |
    +----------------------------+--------------------------------------+-----------------------+

In normal mode, the idle state affects only the sweep transition time
:math:`\tau_{S \rightarrow R}` (see :numref:`tab_a212_transition_times`), not
:math:`C_\text{subsweep}`, so a single value for both idle states.

In HSM, the idle state instead affects :math:`C_\text{subsweep}` directly, so the table gives a
separate value for each configured
:attr:`~acconeer.exptool.a2.SensorConfig.inter_sweep_idle_state`, ARMED and READY.
