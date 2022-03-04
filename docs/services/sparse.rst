.. _sparse-service:

Sparse
======

*The sparse service is ideal for motion-sensing applications requiring high robustness and low power consumption.*

``examples/a111/services/sparse.py`` contains example code on how the Sparse service can be used.

How it works
------------

The other services, :ref:`envelope-service`, :ref:`iq-service`, and :ref:`pb-service`, are all based on sampling the incoming waves several times per wavelength (effectively ~2.5 mm). In sparse, the incoming waves are instead sampled every ~6 **cm**. Therefore, sparse is fundamentally different from the other services. It **does not** simply produce a downsampled version of the :ref:`envelope-service` or :ref:`iq-service` service.

Due to the highly undersampled signal from the sparse service, it should not be used to measure the reflections of static objects. Instead, the sparse service should be used for situations where detecting moving objects is desired. Sparse is optimal for this, as it produces sequences of very robust measurements at the sparsely located sampling points.

.. figure:: /_tikz/res/sparse/over_time.png
   :align: center
   :width: 65%

   An illustration of how the sparse service samples reflected waves from a moving object.

The above image illustrates how a single sparse point samples incoming wavelets from a moving target. The three different blue colored waves are from different points in time, where the darkest one is the most recent (present), and the faded ones are from the past. For every point in time, a sample is taken at the sampling point(s). In this example, there is only one single sample point, but in reality, most often several points are used.

The bottom plot lays out the sampled points over a time scale. In this simple example, the object moves with a steady velocity. As such, over time, the samples will reconstruct the incoming wavelet, which the orange line illustrates.

.. note::
   If the target object is static, the signal too will be static, but not necessarily zero. It can take any value within the peak values of the reflected wave, depending on where on the wave it is sampled.

.. figure:: /_tikz/res/sparse/sweeps_and_frames.png
   :align: center
   :width: 70%

   An illustration of the sparse data frames consisting of a number of sweeps.

From sparse, every received data frame consists of a number of sweeps :math:`N_s` which are sampled after each other. Every sweep consists of one or several (sparse) sampling points in distance as configured. Depending on the configuration, the time between sweeps :math:`T_s` may vary. It can also, within certain limits, be set to a fixed value. Often, we refer to this as the *sweep rate* :math:`f_s=1/T_s` instead of referring to the time between sweeps :math:`T_s`.

Typical sweep rates range between 1 and 50 kHz. On the other hand, typical frame (update) rates :math:`f_f` range between 1 and 200 Hz. Therefore, there often is a large gap between the end of a frame to the beginning of the next one. From a power consumption perspective, this is desirable since it allows the sensor to have a smaller duty cycle. However, if needed, the sparse service can be configured for a near 100% duty cycle.

For many applications, sweeps are sampled closely enough in time that they can be regarded as being sampled simultaneously. In such applications, for example presence detection, the sweeps in each frame can be averaged for optimal SNR.

.. tip::
   Unlike the other services, there is no processing applied to the radar data. Also, it typically produces less data. This makes the sparse service relatively computationally inexpensive and suitable for use with smaller MCU:s.

The sparse service utilizes longer wavelets than the other services, meaning that there will be more energy and therefore better SNR in the received signal. For example, this results in an increased distance coverage for presence detection applications. This also means that a wavelet often spans several sparse points.

How to use
----------

.. tip::
   If this is your first time working with the sparse service, we recommend first getting a feel for how it can be used by running and looking at the :ref:`presence detector<sparse-presence-detection>`.

While the sparse service has a lot of configuration options, they all have sensible defaults for most applications. The only parameters that you really need to set up to get started is the *range* and *frame (update) rate*. Other parameters can be tuned as you go.

If you're doing things like **gesture recognition** or any **velocity measurements**, we recommend using sampling mode A and explicitly setting the *sweep rate*. Also, raising the number of sweeps per frame might be beneficial for such measurements. From there it is also often a good idea to set the *frame (update) rate* as high as possible. Lowering the number of *HWAAS* might be necessary to obtain the desired sweep and/or frame rate.

Configuration parameters
^^^^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: acconeer.exptool.a111.SparseServiceConfig
   :noindex:
   :members:
   :inherited-members:
   :exclude-members: State, SamplingMode, Profile, RepetitionMode

Session info (metadata)
^^^^^^^^^^^^^^^^^^^^^^^

The following information is returned when creating a session.

Data length
   | Python: ``data_length``
   | C SDK: ``data_length``
   | Type: int

   The size of the data frames. For sparse, this is the number of depths times the number of sweeps.

Range start
   | Python: ``range_start_m``
   | C SDK: ``start_m``
   | Type: float
   | Unit: m

   The depth of range start - after rounding the configured range to the closest available sparse sampling points.

Range length
   | Python: ``range_length_m``
   | C SDK: ``length_m``
   | Type: float
   | Unit: m

   The length of the range - after rounding the configured range to the closest available sparse sampling points.

Step length
   | Python: ``step_length_m``
   | C SDK: ``step_length_m``
   | Type: float
   | Unit: m

   The distance in meters between points in the range.

.. _sparse-info-sweep-rate:

Sweep rate
   | Python: ``sweep_rate``
   | C SDK: ``sweep_rate``
   | Type: float
   | Unit: Hz

   The sweep rate. If a sweep rate is explicitly set, this value will be very close to the configured value. If not (the default), this will be the maximum sweep rate.

Data info (result info)
^^^^^^^^^^^^^^^^^^^^^^^

The following information is returned with each data frame.

Missed data
   | Python and C SDK: ``missed_data``
   | Type: int

   Indicates if a data frame was missed, for example due to a too high
   :attr:`~acconeer.exptool.a111.SparseServiceConfig.update_rate`.

Data saturated
   | Python and C SDK: ``data_saturated``
   | Type: bool

   Indication that the sensor has hit its full dynamic range. If this indication is given, the result might be unstable. Most often, the problem is that the gain is set too high.

Disclaimer
----------

The sparse service will have optimal performance using any one of the XM112, XM122 or XM132 Modules. A111 with batch number 10467, 10457 or 10178 (also when mounted on XR111 and XR112) should be avoided when using the sparse service.
