.. _sparse-service:

Sparse
======

.. warning::
   The nomenclature currently differs between the Acconeer SDK and Exploration tool due to backwards compatibility reasons. In the Exploration code base, **frames** are referred to as **sweeps** and **sweeps** are referred to as **subsweeps**. Using frames and sweep is preferred, and will be switched to in Exploration v3. Throughout this guide, we use the preferred nomenclature.

*The sparse service is ideal for motion-sensing applications requiring high robustness and low power consumption.*

How it works
------------

The other services, :ref:`envelope-service`, :ref:`iq-service`, and :ref:`pb-service`, are all based on sampling the incoming waves several times per wavelength (effectively ~2.5 mm). In sparse, the incoming waves are instead sampled every ~6 **cm**. Therefore, sparse is fundamentally different from the other services. It **does not** simply produce a downsampled version of the :ref:`envelope-service` or :ref:`iq-service` service.

Due to the highly undersampled signal from the sparse service, it should not be used to measure the reflections of static objects. Instead, the sparse service should be used for situations where detecting moving objects is desired. Sparse is optimal for this, as it produces sequences of very robust measurements at the sparsely located sampling points.

.. figure:: /_tikz/res/sparse/over_time.png
   :align: center
   :scale: 40%

   An illustration of how the sparse service samples reflected waves from a moving object.

The above image illustrates how a single sparse point samples incoming wavelets from a moving target. The three different blue colored waves are from different points in time, where the darkest one is the most recent (present), and the faded ones are from the past. For every point in time, a sample is taken at the sampling point(s). In this example, there is only one single sample point, but in reality, most often several points are used.

The bottom plot lays out the sampled points over a time scale. In this simple example, the object moves with a steady velocity. As such, over time, the samples will reconstruct the incoming wavelet, which the orange line illustrates.

.. note::
   If the target object is static, the signal too will be static, but not necessarily zero. It can take any value within the peak values of the reflected wave, depending on where on the wave it is sampled.

.. figure:: /_tikz/res/sparse/sweeps_and_frames.png
   :align: center
   :scale: 40%

   An illustration of the sparse data frames consisting of a number of sweeps.

From sparse, every received data frame consists of a number of sweeps :math:`N_s` which are sampled after each other. Every sweep consists of one or several (sparse) sampling points in distance as configured. Depending on the configuration, the time between sweeps :math:`\Delta t_s` may vary. It can also, within certain limits, be set to a fixed value. Often, we refer to this as the *sweep rate* :math:`f_s=1/\Delta t_s` instead of referring to the time between sweeps :math:`\Delta t_s`.

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

Sampling mode
   | Python: ``sampling_mode``
   | C SDK: ``acc_service_sparse_sampling_mode_[get/set]``
   | Type: enum
   | Default: B

   The sampling mode changes how the hardware accelerated averaging is done. Mode A is optimized
   for maximal independence of the depth points, giving a higher depth resolution than mode B.
   Mode B is instead optimized for maximal SNR per unit time spent on measuring. This makes it
   more energy efficient and suitable for cases where small movements are to be detected over long
   ranges. Mode A is more suitable for applications like gesture recognition, measuring the
   distance to a movement, and speed measurements.

   Mode B typically gives roughly 3 dB better SNR per unit time than mode A. However, please note
   that very short ranges of only one or a few points are suboptimal with mode B. In those cases,
   always use mode A.

Range
   | Python: ``range_interval`` (or ``range_start``, ``range_length``, ``range_end``)
   | C SDK: ``acc_sweep_configuration_requested_range_[get/set]``
   | Type: float, float
   | Unit: m

   The measured depth range. The start and end values will be rounded to the closest sparse measurement point available. This roughly results in rounding the values to the closest multiple of 6 cm.

   In Python, ``range_interval`` = ``[range_start, range_end]``.

   In the C SDK, the function takes the start and length.

   The range must be within 0.15 and 7 m. Note that a value of 0.15 m will be rounded to 0.18 m, meaning that the closest possible measurement point is at 18 cm.

Stepsize
   | Python: ``stepsize``
   | C SDK: ``acc_service_sparse_stepsize_[get/set]``
   | Type: int
   | Default: 1

   The step in depth between each data point. A stepsize of 1 corresponds to the finest possible step, which is ~6 cm. A stepsize of 2 samples every other ~6 cm step, i.e., every ~12 cm. 3 gives steps of ~18 cm, and so on.

   Setting a too large stepsize (over 2 or 3) might result in gaps in the data where moving objects "disappear" between sampling points.

   Must be at least 1. Setting a stepsize over 1 might affect the range end point.

Gain
   | Python: ``gain``
   | C SDK: ``acc_sweep_configuration_receiver_gain_[get/set]``
   | Type: float
   | Default: 0.5

   The receiver gain used in the sensor. If the gain is too low, objects may not be visible, or it may result in poor signal quality due to quantization errors. If the gain is too high, strong reflections may saturate the data. We recommend not setting the gain higher than necessary due to signal quality reasons.

   Must be a value between 0 and 1 inclusive, where 1 is the highest possible gain.

Update rate (frame rate)
   | Python: ``sweep_rate`` (old nomenclature)
   | C SDK: ``acc_sweep_configuration_repetition_mode_streaming_[get/set]``
   | Type: float
   | Unit: Hz

   The data frame rate :math:`f_f` from the service.

   .. attention::

      Setting the update rate too high might result in missed data frames.

      The maximum possible update rate depends on the *sweeps per frame* :math:`N_s` and *sweep rate* :math:`f_s`:

      .. math::

         f_f > N_s \cdot f_s + \text{overhead*}

      \* *The overhead largely depends on data frame size and data transfer speeds.*

Sweep rate
   | Python: ``subsweep_rate`` (old nomenclature)
   | C SDK: ``acc_service_sparse_configuration_sweep_rate_[get/set]``
   | Type: float
   | Unit: Hz
   | Default: Unset (highest possible)

   The sparse sweep rate :math:`f_s`. If not set, this will take the maximum possible value.

   The maximum possible sweep rate...

   - Is roughly inversely proportional to the number of depth points measured (affected by **range** and **stepsize**).
   - Is roughly inversely proportional to **HWAAS**.
   - Depends on the **sampling mode**. Mode A is roughly :math:`4/3 \approx 130\%` slower than mode B with the same configuration.

   To get the maximum possible rate, leave this value unset and look at the :ref:`actual sweep rate <sparse-actual-sweep-rate>` in the session info (metadata).

   .. tip::
      If you do not need a specific sweep rate, we recommend leaving it unset.

Sweeps per frame
   | Python: ``number_of_subsweeps`` (old nomenclature)
   | C SDK: ``acc_service_sparse_configuration_sweeps_per_frame_[get/set]``
   | Type: int
   | Default: 16

   The number of sweeps per frame :math:`N_s`.

   Must be at least 1, and not greater than 64 when using sampling mode B.

HWAAS - Hardware Accelerated Average Samples
   | Python: ``hw_accelerated_average_samples``
   | C SDK: ``acc_sweep_configuration_hw_accelerated_average_samples_[get/set]``
   | Type: int
   | Default: 60

   Number of samples taken to obtain a single point in the data. These are averaged directly in the sensor hardware - no extra computations are done in the MCU.

   The time needed to measure a sweep is roughly proportional the HWAAS. Hence, if there's a need to obtain a higher sweep rate, HWAAS could be decreased.

   Must be at least 1 and not greater than 63.

Session info (metadata)
^^^^^^^^^^^^^^^^^^^^^^^

The following information is returned when creating a session.

Data length
   | Python: ``data_length``
   | C SDK: ``data_length``
   | Type: int

   The size of the data frames. For sparse, this is the number of depths times the number of sweeps.

Actual range start
   | Python: ``actual_range_start``
   | C SDK: ``actual_start_m``
   | Type: float
   | Unit: m

   The actual depth of range start - after rounding the configured range to the closest available sparse sampling points.

Actual range length
   | Python: ``actual_range_length``
   | C SDK: ``actual_length_m``
   | Type: float
   | Unit: m

   The actual length of the range - after rounding the configured range to the closest available sparse sampling points.

Actual stepsize
   | Python: ``actual_stepsize``
   | C SDK: ``actual_stepsize_m``
   | Type: float
   | Unit: m

   The actual step size in meters between points in the range.

.. _sparse-actual-sweep-rate:

Actual sweep rate
   | Python: ``actual_subsweep_rate`` (old nomenclature)
   | C SDK: ``actual_sweep_rate``
   | Type: float
   | Unit: Hz

   The actual sweep rate. If a sweep rate is explicitly set, this value will be very close to the configured value. If not (the default), this will be the maximum sweep rate.

Data frame info (result info)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The following information is returned with each data frame.

Sequence number
   | Python and C SDK: ``sequence_number``
   | Type: int

   The sequential number of the returned data frame. If a frame was skipped, for example due to a too high frame (update) rate, the number will increase by two instead of one from the last frame.

Data saturated
   | Python and C SDK: ``data_saturated``
   | Type: bool

   Indication that the sensor has hit its full dynamic range. If this indication is given, the result might be unstable. Most often, the problem is that the gain is set too high.

Disclaimer
----------

The sparse service will have optimal performance using XM112 Module. A111 with batch number 10467, 10457 or 10178 (also when mounted on XR111 and XR112) should be avoided when using the sparse service.
