.. _sparse-service:

Sparse
======

The sparse service allows for detection of any movement, small or large, occurring in front of the sensor at the configured sampling points. Sparse is fundamentally different from the other services as it can not be regarded as a downsampled Envelope or IQ service. Instead of sampling the reflected wavelet several times per wavelength (which is ~5 mm), the wavelet is sampled roughly every 6 cm. As such, the sparse service should not be used to measure the reflections of static objects. Instead, the sparse service produces a sequence of robust measurements of the sparsely located sampling points.

.. image:: /_static/services/sparse.png

The above image illustrates how a single sparse point samples a reflected wavelet from a moving target. To clarify, the three different colored reflections are sampled at different times. Due to the movements of the target, the signal from the sparse service varies over time. If the object is static, the signal too will be static, but could take any value from 0 to the wavelet peak value depending on where the received wavelet is sampled.

Every data frame from the sparse service consists of up to 64 sweeps which are sampled immediately after each other. Every sweep consists of one or several points sampled in distance as configured. Depending on the configuration, the sweeps will be sampled with an interval of roughly 1-100 microseconds. For many applications, they are sampled closely enough in time that they can be regarded as being sampled simultaneously. In such applications, the sweeps in each data frame can be averaged for optimal SNR. Note that unlike the other services, there is no post-processing applied to the data. As post-processing is not needed, this service is relatively computationally inexpensive.

The sparse service is ideal for motion-sensing applications requiring high robustness and low power consumption. Often, less processing is needed as the sparse service outputs a lot less data than the Envelope or IQ service. As a consequence of using less data, much longer ranges can be measured without the use of stitching. Or, if it is important for your application, a higher sweep frequency is also possible. Finally, the sparse service utilizes longer wavelets than the other services, meaning that there will be more energy and better SNR in the received signal. For example, this results in an increased distance coverage for presence detection applications. This also means that a wavelet often spans several sparse points.
