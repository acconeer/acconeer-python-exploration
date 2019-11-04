Services
========

The Acconeer A1 sensor can be used in different modes depending on use case. There are currently four such services optimized for different purposes.

+------------+----------------------------------------+
| Service    | Typical use cases                      |
+============+========================================+
| Power Bins | Low complexity implementations,        |
|            | parking sensor                         |
+------------+----------------------------------------+
| Envelope   | Distance measurements, static target   |
|            | scenes                                 |
+------------+----------------------------------------+
| IQ         | Obstacle detection,                    |
|            | vital sign monitoring                  |
+------------+----------------------------------------+
| Sparse     | Presence detection, hand gesture       |
|            | recognition                            |
+------------+----------------------------------------+


.. toctree::
   :maxdepth: 1
   :glob:

   pb
   envelope
   iq
   sparse


General Service Configuration
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Profiles
~~~~~~~~

The main configuration of all the services are the profiles, numbered 1 to 5. The difference between the profiles is the length of the radar pulse and the way the incoming pulse is sampled. Profiles with low numbers use short pulses while the higher profiles use longer pulses.

Profile 1 is recommended for measuring strong reflectors or distance  measurements in the first couple of decimeters close to the sensor. For distance measurements at longer distances profile 2 and 3 are recommended. Finally, profile 4 and 5 are designed for motion or presence detection at longer distances, where an optimal signal to noise ratio is preferred over an accurate distance measurement.

The previous profile Maximize Depth Resolution and Maximize SNR are now profile 1 and 2. The previous Direct Leakage Profile is obtained by the use of the Maximize Signal Attenuation parameter.


Noise Normalization
~~~~~~~~~~~~~~~~~~~~

With the SW version 2.0.0 release, a sensor signal normalization functionality is activated by default for the Power Bins, Envelope, and IQ Service. This results in a more constant signal for different temperatures and sensors. Applications where the amplitude radar of sweeps are compared to a previously recorded signal or a threshold should see a substantially increase in performance. The radar sweep are normalized to have similar amplitude independent of sensor gain and hardware averaging, resulting in only minor visible effect in the sweeps when adjusting these parameters.

More technically, the functionality is implemented to collect data when starting the service, but not transmitting pulses. This data is then used to determine the current sensitivity of receiving part of the radar by estimating the power level of the noise, which then is used to normalize the collected sweeps. In the most low-power systems, where a service is created to collect just a single short sweep before turning off, the sensor normalization can add a non-negligible part to the power consumption.

Sensor normalization is not implemented in the Sparse service. Instead the Presence detector, using data from the Sparse service, implement this functionality in as similar way.


Hardware Accelerated Average Samples (HWAAS)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

HWAAS is the number of radar pulses averaged within the sensor itself to obtain a single point in the data. A higher HWAAS leads to increased SNR. These pulses are averaged directly in the sensor hardware - no extra data transfer or computations in the MCU.

The time needed to measure a sweep in the sensor is roughly proportional the HWAAS. Hence, if there is a need to obtain a higher sweep rate, HWAAS should be decreased. NOTE: HWAAS does not affect the amount of data transmitted from the sensor over SPI.

The value be at least 1 and not greater than 63.


Gain
~~~~

The receiver gain used in the sensor. If the gain is too low, objects may not be visible, or it may result in poor signal quality due to quantization errors. If the gain is too high, strong reflections may saturate the receiver. We recommend not setting the gain higher than necessary due to signal quality reasons.

Must be a value between 0 and 1 inclusive, where 1 is the highest possible gain.

.. note::
   When Sensor normalization is active, the change in the data due to changing gain is removed after normalization. Therefore, the data might seen unaffected by changes in the gain, except very high (receiver saturation) or very low (quantization error) gain.


Downsampling Factor
~~~~~~~~~~~~~~~~~~~

Each service has a nominal distance spacing between the sampled point. For the Sparse Service, it is close to 6 cm, while for IQ, Envelope, and Power Bins, it is approx 0.5 mm. To get the optimal signal quality all points should be sampled and used in processing. However, only sampling every second, or every fourth, point can substantially reduce the time to collect the sweep and the amount of processing. To achieve this, the downsampling factor can be set to 2 or 4, with default 1.

For the Sparse Service the down-sampling factor can be any positive integer, while for IQ, Envelope, and Power Bins only 1, 2 or 4.
