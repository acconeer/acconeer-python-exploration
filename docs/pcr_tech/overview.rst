########
Overview
########

The Acconeer sensor is a millimeter-wavelength pulsed coherent radar. "Pulsed" means that the sensor transmits a carrier wave during a short period of time, called a wavelet. These transmitted signals are reflected by an object, and the time elapsed between transmission and reception of the reflected signal (:math:`t_{delay}`) is used to calculate the distance to the object using

.. math::
    :label: dist_eq

    d = \frac{t_{delay} v}{2}

.. math::
    :label: eq_speed_of_radar

    v = \frac{c_0}{\sqrt{\varepsilon_r}}

where :math:`\varepsilon_r` is the relative permittivity of the medium. The '2' in the denominator of :eq:`dist_eq` is due to the fact that :math:`t_{delay}` is the time for the signal to travel to the object and back; hence, to get the distance to the object, a division by 2 is needed. The wavelength :math:`\lambda` of the 60.5 GHz carrier frequency :math:`f_\text{RF}` is roughly 5 mm in free space. This means that a 5 mm shift of the received wavelet corresponds to a 2.5 mm shift of the detected object due to the round trip distance.

The term "coherent" means that the returned signal contains both amplitude and phase information, which is useful in many applications. The phase information can, for example, be utilized to detect very small movements or speed. "Coherent" also implies that the starting phase of the transmitted signal is well known, as illustrated in :numref:`fig_transmit_signal_length_a121`. The figure shows a transmitted signal from an Acconeer sensor in the time domain. The timing between each pulse is controlled by the :term:`PRF`, the length of each pulse is controlled by the :term:`Profile` setting, and the carrier frequency of each wavelet is set to 60.5 GHz for all Acconeer products.

.. _fig_transmit_signal_length_a121:
.. figure:: /_static/introduction/fig_transmit_signal_length.png
    :align: center

    Illustration of the time domain transmitted signal from an Acconeer sensor using a :term:`PRF` of 13 MHz. A radar sweep typically consists of thousands of pulses. The length of the pulses can be controlled by setting :term:`Profile`.


Both Acconeer's A111 and A121 sensors are single-channel radars, meaning that they have one TX antenna and one RX antenna. This makes it possible to determine the distance but not the angle to objects. The whole system is integrated into a very small package. More information about the package and its interfaces can be found in the `A111 data sheet <https://developer.acconeer.com/download/a111-datasheet/>`_ and `A121 data sheet <https://developer.acconeer.com/download/a121-datasheet/>`_, respectively.
