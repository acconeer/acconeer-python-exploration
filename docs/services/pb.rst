.. _pb-service:

Power Bins
==========

For use cases with inherently good signal-to-noise ratio the Power Bins service can be used as a low complexity replacement of the :ref:`envelope-service` service. The Power Bins service outputs coarse estimates of the envelope yielding rough estimates of the range-dependent reflectivity in the target scene. By omitting several of the signal processing steps in the :ref:`envelope-service` service the computational footprint is significantly reduced, making this service suitable for small platforms.

``power_bins.py`` contains example code on how the Power Bins service can be used.

.. image:: /_static/services/pb.png

For further reading on the power bins service we refer to the `Power Bins documentation`_ on the `Acconeer developer page`_.

.. _`Power bins documentation`: https://developer.acconeer.com/download/power-bins-service-user-guide-v1-1-pdf/
.. _`Acconeer developer page`: https://developer.acconeer.com/
