.. _envelope-service:

Envelope
========

The Envelope service provides data related to the received energy at different distances from the radar sensor. One envelope measurement is performed by transmitting a sequence radar pulses and measuring the energy content in the returning echoes for a set of time delays from pulse transmission.

The envelope data is a set of :math:`N_D` real valued samples represented as :math:`x[d]`, where :math:`d` is the delay sample index and each value sample has an amplitude :math:`x[d] = A_d` representing the received energy from a specific distance, :math:`d`.

To stabilize the signal and increase the SNR, the sweeps in the Envelope Service can be time filtered. This can be configured by setting the running average factor between 0 and 1, where high number indicates more filtering. The filtering is a standard  `exponential smoothening filter <https://en.wikipedia.org/wiki/Exponential_smoothing>`_ with default setting of 0.7. Note, for very low update rates below a few hertz, the signal from an object moving fast, or suddenly disappearing, remain in the sweep.

The filtering of data in the Envelope Service applies a low-pass filter in the range dimension. This leads to some filter edge effects in the first few centimeters of the sweep. For very short sweeps, approx. 3 cm for Profile 1 and approx 6 cm for Profile 2-5, these edge effects affects the magnitude of the whole sweep. The :ref:`pb-service`, with only a few bins, is recommended for short sweeps.

The Envelope service can be configured with different pulse length profiles, see the :ref:`sensor-intro`.

``examples/a111/services/envelope.py`` contains example code on how this service can be used.

.. figure:: /_static/services/envelope_snr.png
   :align: center
   :width: 90%

.. figure:: /_static/services/envelope_depth.png
   :align: center
   :width: 90%

For further reading on the envelope service we refer to the `Envelope documentation`_ on the `Acconeer developer page`_.

.. _`Acconeer developer page`: https://developer.acconeer.com/
.. _`Envelope documentation`: https://developer.acconeer.com/download/user-guide-envelope-service-pdf/

Configuration parameters
^^^^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: acconeer.exptool.a111.EnvelopeServiceConfig
   :noindex:
   :members:
   :inherited-members:
   :exclude-members: State, Profile, RepetitionMode
