.. _interpreting_radar_data:

Interpreting radar data
=======================

The data produced by the A121 sparse IQ service is conceptually similar to that of the A111 IQ service.
The A121 Sparse IQ data is represented by complex numbers, one for each distance sampled.
Each number has an *amplitude* and a *phase*, the amplitude is obtained by taking the absolute value of the complex number
and the phase is obtained by taking the argument of the same complex number.
A *sweep* is a array of these complex values corresponding to an amplitude and phase of the reflected pulses in the configured range.

For any given frame, we let :math:`z(s, d)` be the complex IQ value (point) for a sweep :math:`s` and a distance point :math:`d`.

.. _fig_a121_data_static:
.. figure:: /_static/handbook/a121/data_static.png
   :align: center
   :width: 80%

   Mocked data of an environment with a single **static** object.

In the simplest case, we have a static environment in the sensor range.
:numref:`fig_a121_data_static` shows an example of this with a single static object at roughly 0.64 m.
The sweeps in the frame have similar amplitude and phase, and the variations are due to random errors.
As such, they could be *coherently* averaged together to linearly increase signal-to-noise ratio (SNR).
In this context, coherently simply means "in the complex plane".

.. _fig_a121_data_moving:
.. figure:: /_static/handbook/a121/data_moving.png
   :align: center
   :width: 80%

   Mocked data of an environment with a single **moving** object.

In many cases, we want to track and/or detect moving objects in the range.
This is demonstrated in :numref:`fig_a121_data_moving`, where the object has moved during the measurement of the frame.
The sweeps still have roughly the same amplitude, but the phase is changing.
Due to this, we can no longer coherently average the sweeps together.
However, we can still (non-coherently) average the amplitudes.

.. _fig_a121_data_moving_slice_polar:
.. figure:: /_static/handbook/a121/data_moving_slice_polar.png
   :align: center
   :width: 50%

   A slice of the mocked data in :numref:`fig_a121_data_moving` of an environment with a single moving object, shown in the complex plane.

To track objects over long distances we may track the amplitude peak as it moves,
but for accurately measuring finer motions we need to look at the phase.
:numref:`fig_a121_data_moving_slice_polar`
shows the slice of the data along the dashed vertical line in :numref:`fig_a121_data_moving`.
Over the 8 sweeps in the example frame, the phase changed ~ 210°.
A full phase rotation of 360° translates to
:math:`\lambda_\text{RF}/2 \approx 2.5 \text{mm}`,
so the 210° corresponds to ~ 1.5 mm.

As evident from the example above, even the smallest movements change the phase and thus move the signal in the complex plane.
This is utilized in for example the *presence detector*, which can detect the presence of humans and animals from their breathing motion.
It can also be used to detect a change in signal very close to the sensor, creating a "touchless button".

.. _fig_a121_data_range_doppler:
.. figure:: /_static/handbook/a121/data_range_doppler.png
   :align: center
   :width: 80%

   Mocked data of a single moving object, transformed into a distance-velocity (a.k.a. range-Doppler) map.

As shown, the complex data can be used to track the relative movement of an object.
By combining this information with the sweep rate, we can also determine its velocity.
In practice, this is commonly done by applying the fast Fourier transform (FFT) to the frame over sweeps,
giving a distance-velocity (a.k.a.\ range-Doppler) map.
:numref:`fig_a121_data_range_doppler` shows an example of this in which we can see an object at
~ 0.64 m with a radial velocity of ~ 0.5 m/s (moving away from the sensor).
This method is commonly used for applications such as
micro and macro gesture recognition,
velocity measurements,
and object tracking.
