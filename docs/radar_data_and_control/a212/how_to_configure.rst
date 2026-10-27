.. _rdac-a212-how-to-configure:

.. include:: ../common/how_to_configure/how_to_configure.rst

Idle-related parameters and control
------------------------------------

Two idle states are available to trade off power consumption during idle periods against measurement setup time:

- **READY** - The deepest idle state. As much of the radar subsystem as possible is shut down.
- **ARMED** - The shallowest idle state. Most of the radar subsystem is kept on.

Because ARMED keeps most of the radar subsystem active, the time to transition from ARMED into a measurement is significantly shorter than from READY.

The idle state is controlled by two parameters:

- **inter sweep idle state** - the idle state the sensor enters between each sweep within a frame.
- **inter frame idle state** - the idle state the sensor enters between frames.

The default value for both parameters is **ARMED**.

If **inter sweep idle state** is set to **READY**, then **inter frame idle state** must also be set to **READY**.

As a general rule, set both idle states to the deepest state that still allows the target sweep and frame rates to be maintained.
Use **ARMED** when low measurement latency or high sweep and frame rates are required, since transitioning from ARMED is significantly faster than from READY.
Use **READY** when minimizing power consumption during idle periods takes priority and the longer transition time is acceptable.

Channel configuration
---------------------

The A212 has 3 transmitter (TX) and 4 receiver (RX) antennas.
By selecting which antennas are active, the measurement is performed over a set of *virtual channels*, each corresponding to one active TX and RX antenna pair.
The number of virtual channels is the product of the number of active TX and RX antennas.
Activating all 3 TX and all 4 RX antennas gives 12 virtual channels, the maximum for the A212.

The active antennas are controlled per subsweep through two bit mask parameters:

- **tx antenna mask** - selects active TX antennas. Bit 0 maps to TX0, bit 1 to TX1, bit 2 to TX2. Setting all three bits (``0b111 = 7``) activates all TX antennas (default). At least one bit must be set.
- **rx antenna mask** - selects active RX antennas. Bit 0 maps to RX0, bit 1 to RX1, bit 2 to RX2, bit 3 to RX3. Setting all four bits (``0b1111 = 15``) activates all RX antennas (default). At least one bit must be set.

**Example 1: single channel (TX0 + RX0 only):**
Set ``tx_antenna_mask = 0b001 = 1`` (bit 0 set, TX0 active) and ``rx_antenna_mask = 0b0001 = 1`` (bit 0 set, RX0 active).
This yields 1 × 1 = **1 virtual channel** (TX0 and RX0 pair).

**Example 2: six channels (TX0, TX1 with RX0, RX1, RX2):**
Set ``tx_antenna_mask = 0b011 = 3`` (bits 0 and 1 set, TX0 and TX1 active) and ``rx_antenna_mask = 0b0111 = 7`` (bits 0, 1, and 2 set, RX0, RX1, and RX2 active).
This yields 2 × 3 = **6 virtual channels** (all TX0/TX1 and RX0/RX1/RX2 pairs).

Different subsweeps within the same sensor configuration may use different antenna masks,
allowing flexible multi-channel configurations within a single frame.
See :ref:`rdac-a212-sweeps-and-frames` for details on how channels appear in the output data.

Other parameters
----------------

- Leave **receiver gain** at the default value and reduce if saturation occurs.
- Leave **enable TX** set (default).
- Leave **jitter compensation** enabled (default) for improved phase stability between sweeps. It occupies one of the five subsweep slots, so a configuration using all five has to disable it. Disable it also when the highest possible sweep rate is required.
