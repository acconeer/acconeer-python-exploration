.. _handbook-a111-system-overview:

System overview
===============

The Acconeer sensor is a mm wavelength pulsed coherent radar, which means that it transmits radio signals in short pulses where the starting phase is well known, as illustrated in :numref:`fig_transmit_signal_length`.

.. _fig_transmit_signal_length:
.. figure:: /_static/introduction/fig_transmit_signal_length.png
    :align: center

    Illustration of the time domain transmitted signal from the Acconeer A111 sensor, a radar sweep typically consists of thousands of pulses. The length of the pulses can be controlled by setting Profile.

These transmitted signals are reflected by an object and the time elapsed between transmission and reception of the reflected signal (:math:`t_{delay}`) is used to calculate the distance to the object by using

.. math::
    :label: eq_dist

    d=\frac{t_{delay}v}{2}

.. math::
    :label: eq_speed_of_light

    v=\frac{c_0}{\sqrt{\varepsilon_r}}

where :math:`\varepsilon_r` is the relative permittivity of the medium. The '2' in the denominator of :eq:`eq_dist` is due to the fact that :math:`t_{delay}` is the time for the signal to travel to the object and back, hence to get the distance to the object a division by 2 is needed, as illustrated in :numref:`fig_sensor_wave_object`.
The wavelength :math:`\lambda` of the 60.5 GHz carrier frequency :math:`f_\text{RF}` is roughly 5 mm in free space.
This means that a 5 mm shift of the received wavelet corresponds to a 2.5 mm shift of the detected object due to the round trip distance.

:numref:`fig_block_diagram` shows a block diagram of the A111 sensor. The signal is transmitted from the Tx antenna and received by the Rx antenna, both integrated in the top layer of the A111 package substrate. In addition to the mmWave radio the sensor consists of power management and digital control, signal quantization, memory and a timing circuit.

.. _fig_block_diagram:
.. figure:: /_static/introduction/fig_block_diagram.png
    :align: center

    Block diagram of the A111 sensor package, further details about interfaces can be found in the A111 data sheet.

:numref:`fig_envelope_2d` shows a typical radar sweep obtained with the Envelope Service, with one object present. The range resolution of the measurement is ~0.5 mm and each data point correspond to transmission of at least one pulse (depending on averaging), hence, to sweep 30 cm, e.g. from 20 cm to 50 cm as in :numref:`fig_envelope_2d`, requires that 600 pulses  are transmitted. The system relies on the fact that the pulses are transmitted phase coherent, which makes it possible to send multiple pulses and then combine the received signal from these pulses to improve signal-to-noise ratio (SNR) to enhance the object visibility.

.. _fig_envelope_2d:
.. figure:: /_static/introduction/fig_envelope_2d.png
    :align: center

    Output from Envelope service for a typical radar sweep with one object present.
