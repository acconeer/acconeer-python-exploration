.. _rdac-a212-control:

Control
=======

This page describes how the A212 is controlled from its host.

Fundamentals
------------

In the basic way of operating the A212,
the process goes through 3 repeating stages:

#. **Measure**: The host signals the sensor to start measuring. The interrupt pin will go low, and then high again when the sensor completes the measurement.
#. **Wait for interrupt**: The host waits for the interrupt indicating that said measurement is finished.
#. **Read**: The host reads out the data from said measurement.

In this mode, the rate of frame measurements is effectively given by the rate of the *measure* call.
The A212 is also capable of triggering itself,
giving an accurate rate.
This is done by setting the :attr:`~acconeer.exptool.a2.SensorConfig.frame_rate` in configuration.
In this case, the sensor will not start its measurement until the corresponding time has passed.

If the host responds with the *measure* call after the timer ends,
the frame measurement will be delayed.
To avoid this, the host must read out the data and issue the next *measure* call before
the frame timer expires.

Rate control
------------

The A212 exposes two rate parameters:

- :attr:`~acconeer.exptool.a2.SensorConfig.sweep_rate`: the rate at which sweeps are acquired
  within a frame. Only applicable when ``sweeps_per_frame`` > 1.
- :attr:`~acconeer.exptool.a2.SensorConfig.frame_rate`: the rate at which frames are acquired.
  When not set, the sensor measures as fast as the host commands it to.

Between frames, the sensor idles in the state configured by
:attr:`~acconeer.exptool.a2.SensorConfig.inter_frame_idle_state`.
Between sweeps within a frame, the sensor idles in the state configured by
:attr:`~acconeer.exptool.a2.SensorConfig.inter_sweep_idle_state`.
Lower idle states consume less power but require more time to transition back to the measure state,
affecting the achievable sweep and frame rates.

.. seealso::

   :ref:`rdac-a212-timing` for the transition times between idle states and their impact on
   frame and sweep duration.
