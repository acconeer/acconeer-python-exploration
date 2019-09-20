.. _sparse-presence-detection:

Presence detection (sparse)
===========================

.. warning::
   The nomenclature currently differs between the Acconeer SDK and Exploration tool due to backwards compatibility reasons. In the Exploration code base, **frames** are referred to as **sweeps** and **sweeps** are referred to as **subsweeps**. Using frames and sweep is preferred, and will switched to in Exploration v3. Throughout this guide, we use the preferred nomenclature.

A presence detection algorithm built on top of the :ref:`sparse-service` service - based on measuring changes in the radar response over time.

The :ref:`sparse-service` service returns data frames in the form of :math:`N_s` sweeps, each consisting of :math:`N_d` range depth points, normally spaced roughly 6 cm apart. We denote frames captured using the sparse service as :math:`x(f,s,d)`, where :math:`f` denotes the frame index, :math:`s` the sweep index and :math:`d` the range depth index. As described in the documentation of the :ref:`sparse-service` service, small movements within the field of view of the radar appear as sinusoidal movements of the sampling points over time. Thus, for each range depth point, we wish to detect changes between individual point samples occurring in the :math:`f` and :math:`s` dimensions.

This presence detection algorithm achieves this by depthwise looking at the deviation between a fast and a slow low pass filtered version of the signal. This deviation is then filtered again both in time and depth. To be more robust against changing environments and variations between sensors, a normalization is done against the noise floor.

Plots
-----

.. image:: /_static/processing/sparse_presence.png

The above image shows a screenshot of the detector plots. In it, we can a target detected at around 0.5 m.

**Top plot:**
The frame :math:`x` (blue dots), along with the fast (orange) and slow (green) filtered sweep mean
:math:`\bar{y}_\text{fast}` and :math:`\bar{y}_\text{slow}` respectively.
The distance between the fast (orange) and slow (green) dots is the basis for this detector.

**Middle plot:**
The "depthwise presence" :math:`z`. This signal is the time and depth filtered (and noise normalized) version of the distance between the fast and slow filter.

**Bottom plot:**
The detector output :math:`\bar{v}`. Typically limited to give a clearer view. This is basically a time filtered maximum of the above plot.

**Not shown:** The noise estimation :math:`\bar{n}`, used for normalization of the signal.

Detailed description
--------------------

Inter-frame detection basis
^^^^^^^^^^^^^^^^^^^^^^^^^^^

In the typical case, the time between *frames* is far greater than the time between *sweeps*. Typically, the frame rate is 5 - 100 Hz while the sweep rate is 3 - 30 kHz. Therefore, when looking for slow movements - presence - the sweeps in a frame can be regarded as being sampled at the same point in time. This allows us to take the mean over all sweeps in a frame without loosing any information. Let the *mean sweep* be denoted as

.. math::
   y(f, d) = \frac{1}{N_s} \sum_s x(f, s, d)

We take this mean sweep :math:`y` and depthwise run it though two `exponential smoothing`_ filters (first order IIR filters). One slower filter with a larger `smoothing factor`_, and one faster filter with a smaller smoothing factor. Let :math:`\alpha_\text{fast}` and :math:`\alpha_\text{slow}` be the smoothing factors and :math:`\bar{y}_\text{fast}` and :math:`\bar{y}_\text{slow}` be the filtered sweep means.
In the implementation, the smoothing factors :math:`\alpha_\text{fast}` and :math:`\alpha_\text{slow}` are set through the
:attr:`~examples.processing.presence_detection_sparse.ProcessingConfiguration.fast_cutoff`
and
:attr:`~examples.processing.presence_detection_sparse.ProcessingConfiguration.slow_cutoff`
parameters.
The relationship between cutoff frequency and smoothing factor is described under :ref:`calculating-smoothing-factors`.
For every depth :math:`d`, for every new frame :math:`f`:


.. math::
   \bar{y}_\text{slow}(f, d) = \alpha_\text{slow} \cdot \bar{y}_\text{slow}(f-1, d) + (1 - \alpha_\text{slow}) \cdot y(f, d)

   \bar{y}_\text{fast}(f, d) = \alpha_\text{fast} \cdot \bar{y}_\text{fast}(f-1, d) + (1 - \alpha_\text{fast}) \cdot y(f, d)

From the fast and slow filtered sweep means, a deviation metric :math:`s` is obtained by taking the absolute deviation between the two:

.. math::
   s(f, d) = |\bar{y}_\text{fast}(f, d) - \bar{y}_\text{slow}(f, d)|

Basically, :math:`s` relates to the instantaneous power of a bandpass filtered version of :math:`y`. This metric is then filtered again with a smoothing factor :math:`\alpha_\text{dev}`, set through the
:attr:`~examples.processing.presence_detection_sparse.ProcessingConfiguration.deviation_tc`
parameter,
to get a more stable metric:

.. math::
   \bar{s}(f, d) = \alpha_\text{dev} \cdot \bar{s}(f-1, d) + (1 - \alpha_\text{dev}) \cdot s(f, d)

This is the starting point of the inter-frame presence detection algorithm. In a few words - depthwise low pass filtered power of the bandpass filtered signal. But before it's used, it's favorable to normalize it with noise floor, discussed in the following section.

Noise estimation
^^^^^^^^^^^^^^^^

To normalize detection levels, we need an estimate of the noise power generated by the sensor. We assume that from a static channel, i.e., a radar signal with no moving reflections, the noise is white and its power is its variance. However, we do not want to rely on having such a measurement to obtain this estimate.

Since we're looking for motions generated by humans and other living things, we know that we typically won't see fast moving objects in the data. In other words, we may assume that *high frequency content in the data originates from sensor noise*.
Since we have a relatively high sweep rate, we may take advantage of this to measure high frequency content.

Extracting the high frequency content from the data can be done in numerous ways. The simplest to implement is possibly a FFT, but it is computationally expensive. Instead, we use another technique which is both robust and cheap.

First, to remove any trends from fast motion in the frame, we differentiate over the sweeps :math:`N_\text{diff}=3` times:

.. math::
   x'(f, s, d) = x^{(1)}(f, s, d) = x(f, s, d) - x(f, s - 1, d)

.. math::
   ...

.. math::
   x^{(N_\text{diff})}(f, s, d) = x^{(N_\text{diff} - 1)}(f, s, d) - x^{(N_\text{diff} - 1)}(f, s - 1, d)


Then, take the mean absolute deviation:

.. math::
   \hat{n}(f, d) = \frac{1}{N_s - N_\text{diff}} \sum_{s=N_\text{diff}}^{N_s} | x^{(N_\text{diff})}(f, s, d) |

And normalize such that the expectation value would be the same as if no differentiation was applied:

.. math::
   n(f, d) = \hat{n}(f, d)
   \cdot
   \left[
       \sum_{k=0}^{N_\text{diff}} \binom{N_\text{diff}}{k}^2
   \right]^{-1/2}

Finally, apply an exponential smoothing filter with a smoothing factor :math:`\alpha_\text{noise}`, set through the
:attr:`~examples.processing.presence_detection_sparse.ProcessingConfiguration.noise_tc`
parameter,
to get a more stable metric:

.. math::
   \bar{n}(f, d) = \alpha_\text{noise} \cdot \bar{n}(f-1, d) + (1 - \alpha_\text{noise}) \cdot n(f, d)

Generating the detector output
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

With the noise estimate :math:`\bar{n}`, we form a depthwise normalized inter-frame detection:

.. math::
   \bar{s}_n(f, d) = \frac{\bar{s}(f, d) \cdot \sqrt{N_s}}{\bar{n}(f, d)}

Finally, since the reflection typically span several depth points, we apply a small depth filter:

.. math::
   z(f, d) = \frac{1}{3} \sum_{i=-1}^{1} \bar{s}_n(f, d + i)

where the signal :math:`\bar{s}_n` is zero-padded, i.e.:

.. math::
   \bar{s}_n(f, d) = 0 \text{ for } d \lt 1 \text{ and } d \gt N_d

From :math:`z`, we can extract the information we are looking for. Is there someone present in front of the sensor, and if so, where? To answer this, we simply look for a peak in the data :math:`z`. To give the detection decision a bit of inertia, we also add a smoothing filter to the peak value.

.. math::
   v(f) = \max_d(z(f, d))

.. math::
   \bar{v}(f) = \alpha_\text{output} \cdot \bar{v}(f-1) + (1 - \alpha_\text{output}) \cdot v(f)

.. math::
   p = v > v_\text{threshold}

.. math::
   d_p = \arg\max_d(z(f, d))

where :math:`p` is the "present"/"not present" output and :math:`d_p` is the presence depth index output.

It is possible to tune :math:`\alpha_\text{output}` through the
:attr:`~examples.processing.presence_detection_sparse.ProcessingConfiguration.output_tc`
parameter. The threshold :math:`v_\text{threshold}` is settable through the
:attr:`~examples.processing.presence_detection_sparse.ProcessingConfiguration.threshold`
parameter.

Overview
^^^^^^^^

.. graphviz:: /graphs/presence_detection_sparse.dot
   :align: center

.. _calculating-smoothing-factors:

Calculating smoothing factors
-----------------------------

Instead of directly setting the smoothing factor of the smoothing filters in the detector, we use cutoff frequencies and time constants. This allows the configuration to be independent of the frame rate.

The symbols used are:

============== ================ ========
**Symbol**     **Description**  **Unit**
-------------- ---------------- --------
:math:`\alpha` Smoothing factor 1
:math:`\tau`   Time constant    s
:math:`f_c`    Cutoff frequency Hz
:math:`f_f`    Frame rate       Hz
============== ================ ========

Going from time constant :math:`\tau` to smoothing factor :math:`\alpha`:

.. math::
   \alpha = \exp\left(-\frac{1}{\tau \cdot f_f}\right)

The bigger the time constant, the slower the filter.

Going from cutoff frequency :math:`f_c` to smoothing factor :math:`\alpha`:

.. math::
   \alpha =
   \begin{cases}
   2 - \cos(2\pi f_c/f_f) - \sqrt{\cos^2(2\pi f_c/f_f) - 4 \cos(2\pi f_c/f_f) + 3} & \text{if } f_c < f_f / 2 \\
   0 & \text{otherwise} \\
   \end{cases}

The lower the cutoff frequency, the slower the filter. The expression is obtained from setting the -3 dB frequency of the resulting exponential filter to be the cutoff frequency. For low cutoff frequencies, the more well known expression :math:`\alpha = \exp(-2\pi f_c/f_f)` is a good approximation.

Read more:
`time constants <https://en.wikipedia.org/wiki/Exponential_smoothing#Time_Constant>`_,
`cutoff frequencies <https://www.dsprelated.com/showarticle/182.php>`_.

Configuration
-------------

.. autoclass:: examples.processing.presence_detection_sparse.ProcessingConfiguration
   :members:

.. _`exponential smoothing`: https://en.wikipedia.org/wiki/Exponential_smoothing
.. _`smoothing factor`: https://en.wikipedia.org/wiki/Exponential_smoothing
