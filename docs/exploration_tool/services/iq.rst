.. _iq-service:

IQ
==

The IQ service utilizes the phase-coherency of the Acconeer pulsed radar to produce stable In-phase and Quadrature (IQ) components, capable of detecting fine movement occurring in a target scene. Such micro-motions can be used in, for instance, presence detection in front of the sensor, detection of breathing rate and obstacle detection.

The In-phase and Quadrature components are represented as complex values, generating a complex set of :math:`N_D` samples represented as :math:`x[d]`, where :math:`d` is the delay sample index. Each complex value has an amplitude and a phase as in :math:`x[d] = A_de^{i\phi_d}`. A :math:`2\pi` phase rotation of an IQ data point corresponds to a movement at the specific distance of :math:`\lambda/2 \approx 2.5` mm, providing high relative spatial resolution.

Similarly to the :ref:`envelope-service` service the amplitudes obtained through the IQ service provide a method for examining the reflectivity at different distances from the radar sensor. These two services are however differently optimized. The :ref:`envelope-service` service is optimized for providing an accurate envelope estimate, while the IQ service is optimized for producing a phase-stable estimate. Thus, one should only use the IQ service if phase information is of importance.

For phase estimation in the vital sign use case and for object detection in the robot use case, Profile 2 and 3 are recommended. To get data good data from the IQ service with Profile 1, sampling mode B and a Hardware accelerated average samples (HWAAS) of at least 20.

The filtering of data in the IQ Service applies a low-pass filter in the range dimension. This leads to some filter edge effects in the first few centimeters of the sweep. For very short sweeps, approx. 3 cm for Profile 1 and approx 6 cm for Profile 2-5, these edge effects affects the magnitude and phase of the whole sweep. It is therefore recommended to add at least 3 cm to the sweep at each end for Profile 1, and 6 cm for Profile 2-5, to the region where the amplitude and phase should be estimated.

The IQ service can be configured with different pulse length profiles, see the :ref:`sensor-intro`.

Detection of micro-motions using the IQ service in a target scene has many use cases,
some of which are presented in :ref:`sleep-breathing`, :ref:`obstacle-detection`, and :ref:`phase-tracking`.

``examples/a111/services/iq.py`` contains example code on how the IQ service can be used.

.. figure:: /_static/services/iq.png
   :align: center
   :width: 90%

For further reading on the IQ service we refer to the `IQ documentation`_ on the `Acconeer developer page`_.

.. _`IQ documentation`: https://developer.acconeer.com/download/iq-data-service-user-guide-pdf/
.. _`Acconeer developer page`: https://developer.acconeer.com/

Configuration parameters
^^^^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: acconeer.exptool.a111.IQServiceConfig
   :noindex:
   :members:
   :inherited-members:
   :exclude-members: State, Profile, RepetitionMode
