.. _envelope-service:

Envelope
========

The Envelope service provides data related to the reflectivity at different distances from the radar sensor. One envelope measurement is performed by transmitting a sequence radar pulses and measuring the energy content in the returning echoes for a set of time delays from pulse transmission.

``envelope.py`` contains example code on how this service can be used. The envelope service can be run in two different modes: ``MAX_SNR`` and ``MAX_DEPTH_RESOLUTION``. ``MAX_SNR`` transmits longer radar pulses generating returning echoes high in energy and hence produces a good signal-to-noise ratio (SNR). ``MAX_DEPTH_RESOLUTION`` utilizes shorter pulses which instead provides better distance resolution at the cost of a reduced SNR. In below figures the same target object is viewed in each of the two envelope modes.

.. image:: /_static/services/envelope_snr.png
.. image:: /_static/services/envelope_depth.png

For further reading on the envelope service we refer to the `Envelope documentation`_ on the `Acconeer developer page`_.

.. _`Acconeer developer page`: https://developer.acconeer.com/
.. _`Envelope documentation`: https://developer.acconeer.com/download/envelope-service-user-guide-v1-3-pdf/
