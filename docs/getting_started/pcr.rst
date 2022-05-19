Pulsed Coherent Radar
^^^^^^^^^^^^^^^^^^^^^

Radar is a well-established technology which has been used in many different applications where accurate and robust distance measurement is required. You can find radar in cars, in the process industry, in airplanes etc. However, most often these radar systems are big, power hungry and expensive, what Acconeer offer is a way to take radar into applications where size, cost and power consumption matter.
Radar is an acronym for Radio Detection and Ranging and is a way of determining range to an object by transmitting and detecting radio waves. Acconeer’s radar system is a time-of-flight system, which means that a radio wave is transmitted by a first antenna, reflected by an object, and then received by a second antenna. The time of flight between transmission and reception of the signal is measured, as illustrated in :numref:`fig_sensor_wave_object`.

.. _fig_sensor_wave_object:
.. figure:: /_static/introduction/fig_sensor_wave_object.png
    :align: center

    Illustration of the pulsed coherent radar system where the time of flight is measured to determine distance to object

The distance to the object can then be calculated by multiplying the time-of-flight with the speed of the radio wave (same as speed of light) and then dividing by two as the distance the signal has traveled is equal to two times the distance to the object. More details about the radar and the Acconeer approach can be found in the :ref:`sensor-intro-system-overview`.

There are different approaches to building radar systems, each with its own pros and cons that typically results in a trade-off between accuracy and power consumption, see :numref:`fig_pulsed_coherent_radar`. At Acconeer we have solved this by combining two important features of a radar system, the first is that it is pulsed, which means that the radio part is shut down in between transmission of signals. In fact, the Acconeer radar is pulsed so fast that, typically, the radio is active less than 1 % of the time even when transmitting at maximum rate. This is how the power consumption can be kept low and optimized dependent on the update rate required by your application.

.. _fig_pulsed_coherent_radar:
.. figure:: /_static/introduction/fig_pulsed_coherent_radar.png
    :align: center
    :width: 60%

    Pulsed coherent radar.

The second feature is that it is coherent, which means that each transmitted signal has a stable time and phase reference on the pico second scale, which allows for high accuracy measurements. Coherent radar systems usually rely on a continuous generation of the radio signal, which consumes a lot of current independent on update rate, hence one of the innovations Acconeer has made is to combine the benefits of pulsed systems and the benefits of coherent systems into one product, the Pulsed Coherent Radar (PCR).
The unique selling points of the PCR sensor are summarized in :numref:`fig_unique_selling_points`. The sensor makes it possible to perform high accuracy measurements while consuming very little power and the fast pulsing of the system makes it possible to track fast movements.

.. _fig_unique_selling_points:
.. figure:: /_static/introduction/fig_unique_selling_points.png
    :align: center
    :width: 85%

    Unique selling points of the Acconeer pulsed coherent radar.

Another benefit of the pulse coherent radar is that amplitude, time and phase of the received signal can be handled separately and allow for classification of different materials that the signal has been reflected on. These are all benefits when compared to sensors such as infra-red and ultrasonic. Additional benefits are that the Acconeer radar can be hidden behind colored plastic or glass and hence do not need an open or visible aperture, we call this optimized integration. The sensor is also robust as it is not sensitive to ambient light or sound and not sensitive to dust or even color of the object.
