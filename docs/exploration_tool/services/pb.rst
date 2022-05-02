.. _pb-service:

Power Bins
==========

The Power Bins service provides data related to the received energy at different distances from the radar sensor. One Power Bins measurement is performed by transmitting a sequence radar pulses and measuring the energy content in the returning echoes for a set of time delays from pulse transmission.

The Power Bins Service is mainly intended for use in low power applications where large objects are measured at short distances from the radar sensor, e.g. in parking sensors mounted on the ground detecting cars. Hence, for use cases with inherently good signal-to-noise ratio the Power Bins service can be used as a low complexity replacement of the :ref:`envelope-service` service.

The power bins values are calculated using an algorithm optimized for low computational complexity, however this algorithm will not suppress noise as much as the more advanced signal processing algorithms used in the Envelope and IQ Data Services. For use cases with inherently good signal-to-noise ratio the Power Bin service can be used as a low complexity replacement of the :ref:`envelope-service` service. The Power Bin service outputs coarse estimates of the envelope yielding rough estimates of the range-dependent reflectivity in the target scene. By omitting several of the signal processing steps in the :ref:`envelope-service` service the computational footprint is significantly reduced, making this service suitable for small platforms.

For use cases with weaker radar echoes, i.e., lower SNR, or when the resolution of the signal is important, we recommend using the Envelope, IQ or Sparse data service instead.

The Power Bins service can be configured with different pulse length profiles, see the :ref:`sensor-intro`.

``examples/a111/services/power_bins.py`` contains example code on how the Power Bins service can be used.

.. figure:: /_static/services/pb.png
   :align: center
   :width: 90%

For further reading on the power bins service we refer to the `Power Bins documentation`_ on the `Acconeer developer page`_.

.. _`Power bins documentation`: https://developer.acconeer.com/download/power-bins-service-user-guide-pdf/
.. _`Acconeer developer page`: https://developer.acconeer.com/

Configuration parameters
^^^^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: acconeer.exptool.a111.PowerBinServiceConfig
   :noindex:
   :members:
   :inherited-members:
   :exclude-members: State, Profile, RepetitionMode
