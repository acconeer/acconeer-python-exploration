.. _rdac-a212-sweeps-and-frames:

.. include:: ../common/sweeps_and_frames.rst

TX and RX execution order
^^^^^^^^^^^^^^^^^^^^^^^^^

For A212, the measurement execution order described above extends to
multiple antennas within each subsweep. For each distance point, the
sensor steps through the active TX antennas in the order TX0, TX1, TX2.
For each TX transmission, all active RX antennas receive simultaneously,
producing one IQ sample per RX antenna. This sequence is repeated for
every distance point and every sweep in the frame.

Channel representation
----------------------

Each active TX and RX antenna pair forms one *virtual channel*.
A frame therefore has three dimensions: sweeps, channels, and distance points, as illustrated below.

.. _fig_a212_channel_stack:
.. figure:: /_tikz/res/handbook/a212/sweep_and_frame_illustration.png
   :align: center
   :width: 70%

   A frame contains :math:`N_s` sweeps, each composed of one or more subsweeps (inner green bars) within
   a sweep envelope (outer orange bar). Data is collected for :math:`N_c` virtual channels (stacked
   dimension) at :math:`N_d` distance points per sweep.

Channel numbering
^^^^^^^^^^^^^^^^^

Channels are numbered in TX-major order:

.. math::

   \text{channel number} = \text{TX index} \times N_{RX} + \text{RX index}

where :math:`N_{RX} = 4` is the total number of RX antennas on the A212.

With all antennas active (``tx_antenna_mask = 0b111``, ``rx_antenna_mask = 0b1111``),
channels 0 through 11 are assigned as follows:

.. table:: TX-major channel numbers (all antennas active)
    :align: center
    :widths: auto

    +----------+-----+-----+-----+-----+
    |          | RX0 | RX1 | RX2 | RX3 |
    +==========+=====+=====+=====+=====+
    | **TX0**  | 0   | 1   | 2   | 3   |
    +----------+-----+-----+-----+-----+
    | **TX1**  | 4   | 5   | 6   | 7   |
    +----------+-----+-----+-----+-----+
    | **TX2**  | 8   | 9   | 10  | 11  |
    +----------+-----+-----+-----+-----+

When only a subset of antennas is active, only the corresponding channel numbers appear.
For example, with ``tx_antenna_mask = 0b101`` (TX0 and TX2), channels 4-7 are absent and
the active channel numbers are 0-3 and 8-11.

Frame data layout
^^^^^^^^^^^^^^^^^

:py:class:`~acconeer.exptool.a2.Result` exposes frame data as a 2D array of shape
``(sweeps_per_frame, columns_per_sweep)``, where ``columns_per_sweep`` is the concatenation
of all subsweeps of :math:`\text{num\_points} \times \text{num\_channels}`.

Within each subsweep block of columns, data is arranged point by point.
For each distance point, all active channels are stored consecutively in TX-major order:

.. code-block:: text

    subsweep 0 columns:
    [ pt0_ch0, pt0_ch1, ..., pt0_ch(N-1), pt1_ch0, ..., pt(M-1)_ch(N-1) ]

    subsweep 1 columns (if present):
    [ pt0_ch0, ... ]

where M is ``num_points`` and N is the number of active channels for that subsweep,
and channel indices are TX-major within the active set.

Use :py:meth:`~acconeer.exptool.a2.Result.get_subframe` to extract the data for a specific
subsweep as a ``(sweeps_per_frame, num_points * num_channels)`` array.
Pass ``channel_indexes`` to select a subset of channels by TX-major channel index.

.. seealso::

   :ref:`rdac-a212-how-to-configure` for antenna mask configuration and channel count.

Limitations
-----------

Unlike A121, A212 does not have a fixed frame buffer that caps the total number of IQ samples.
The frame buffer is allocated dynamically in host SRAM, so the practical upper bound depends on
available memory on the host platform.

The individual parameters are bounded as follows:

- **sweeps per frame**: 1 to 512.
- **subsweeps**: 1 to 5 per sensor configuration. When jitter compensation is enabled it
  takes one of the slots, leaving 4 for the application.
- **num points**: 1 to 65535 per subsweep.
- **virtual channels**: 1 to 12 per subsweep (up to 3 TX times up to 4 RX).

The total frame data in bytes is
:math:`\text{sweeps\_per\_frame} \times \sum_{\text{ss}} (\text{num\_points}_{\text{ss}} \times \text{num\_channels}_{\text{ss}}) \times 4`.
