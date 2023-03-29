.. _handbook-a121-csm:

Continuous sweep mode (CSM)
===========================

With CSM, the sensor timing is set up to generate a continuous stream of sweeps, even if more than one sweep per frame is used.
The interval between the last sweep in one frame to the first sweep in the next frame becomes equal to the interval between sweeps within a frame (given by the sweep rate).

It ensures that:

.. math::
   \text{frame rate} = \frac{\text{sweep rate}}{\text{sweeps per frame}}

While the frame rate parameter can be set to approximately satisfy this condition, using CSM is more precise.

If only one sweep per frame is used, CSM has no use since a continuous stream of sweeps is already given (if a fixed frame rate is used).

The main use for CSM is to allow reading out data at a slower rate than the sweep rate, while maintaining that sweep rate continuously.

Note that in most cases, :attr:`~acconeer.exptool.a121.SensorConfig.double_buffering` must be enabled to allow high rates without delays.

Examples of where CSM is used are the :doc:`Vibration measurement app</exploration_tool/algo/a121/examples/vibration>` and the :doc:`Phase tracking app</exploration_tool/algo/a121/examples/phase_tracking>`.
In both cases, it is desirable to have a continuous stream of sweeps at a fixed rate with a configurable frame rate.

CSM is enabled through the sensor configuration parameter :attr:`~acconeer.exptool.a121.SensorConfig.continuous_sweep_mode`.

Constraints:

- :attr:`~acconeer.exptool.a121.SensorConfig.frame_rate` must be set to unlimited (None).

- :attr:`~acconeer.exptool.a121.SensorConfig.sweep_rate` must be set (> 0).

- :attr:`~acconeer.exptool.a121.SensorConfig.inter_sweep_idle_state` must be set equal to :attr:`~acconeer.exptool.a121.SensorConfig.inter_frame_idle_state`.
