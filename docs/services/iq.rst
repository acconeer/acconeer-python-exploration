.. _iq-service:

IQ
==

The IQ service utilizes the phase-coherency of the Acconeer pulsed radar to produce stable In-phase and Quadrature (IQ) components, capable of detecting fine movement occurring in a target scene. Such micro-motions can be used in, for instance, presence detection in front of the sensor, detection of breathing rate and obstacle detection.

The In-phase and Quadrature components are represented as complex values, generating a complex set of :math:`N_D` samples represented as :math:`x[d]`, where :math:`d` is the delay sample index. Each complex value has an amplitude and a phase as in :math:`x[d] = A_de^{i\phi_d}`. A :math:`2\pi` phase rotation of an IQ data point corresponds to a movement at the specific distance of :math:`\lambda/2 \approx 2.5` mm, providing high relative spatial resolution.

Similarly to the :ref:`envelope-service` service the amplitudes obtained through the IQ service provide a method for examining the reflectivity at different distances from the radar sensor. These two services are however differently optimized. The :ref:`envelope-service` service is optimized for providing an accurate envelope estimate, while the IQ service is optimized for producing a phase-stable estimate. Thus, one should only use the IQ service if phase information is of importance.

``iq.py`` contains example code on how the IQ service can be used. Detection of micro-motions using the IQ service in a target scene has many use cases, some of which are presented in ``breathing.py``, ``sleep_breathing.py``, ``obstacle_detection.py``, and ``phase_tracking.py``.

.. image:: /_static/services/iq.png

For further reading on the IQ service we refer to the `IQ documentation`_ on the `Acconeer developer page`_.

.. _`IQ documentation`: https://developer.acconeer.com/download/iq-data-service-user-guide-v1-0-pdf/
.. _`Acconeer developer page`: https://developer.acconeer.com/
