Presence detection
==================

This presence detector measures changes in the data over time to detect motion. It is divided into two separate parts:

Intra-frame presence -- detecting (faster) movements *inside* frames
   For every frame and depth, the intra-frame deviation is based on the deviation from the mean of the sweeps

Inter-frame presence -- detecting (slower) movements *between* frames
   For every frame and depth, the absolute value of the mean sweep is filtered through a fast and a slow low pass filter.
   The inter-frame deviation is the deviation between the two filters and this is the base of the inter-frame presence.
   As an additional processing step, it is possible to make the detector even more sensitive to very slow motions, such as breathing.
   This utilizes the phase information by calculating the phase shift in the mean sweep over time.
   By weighting the phase shift with the mean amplitude value, the detection of slow moving objects will increase.


Both the inter- and the intra-frame deviations are filtered both in time and depth. Also, to be more robust against changing environments and variations between sensors, normalization is done against the noise floor.
Finally, the output from each part is the maximum value in the measured range.

Presence detected is defined as either inter- or intra-frame detector having a presence score above chosen thresholds.

How to use
----------

Tuning the sensor parameters
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
First, the range of detection needs to be determined. Based on the start range,
:attr:`~acconeer.exptool.a121.algo.presence._detector.DetectorConfig.start_m`,
a best fit for the profile is calculated.
The profile is set to the biggest profile with no direct leakage in the chosen range. This is to maximize SNR.
The shortest start range needed for the different profiles can be found in :numref:`tab_a121_profile_start_range`:

.. _tab_a121_profile_start_range:
.. table:: Minimum start range for different profiles.
   :align: center
   :widths: auto

   +---------+-------------+
   | Profile | Start range |
   +=========+=============+
   | 1       | 0 m         |
   +---------+-------------+
   | 2       | 0.29 m      |
   +---------+-------------+
   | 3       | 0.57 m      |
   +---------+-------------+
   | 4       | 0.77 m      |
   +---------+-------------+
   | 5       | 1.29 m      |
   +---------+-------------+

.. note::
   To maximize SNR in long range detections, the start range needs to be set greater than 1.28 m.

For each profile a half power pulse width can be calculated based on the pulse length. We choose the
:attr:`~acconeer.exptool.a121.algo.presence._detector.DetectorConfig.step_length`
to not exceed this value, while still having it as long as possible.
We want the step length as long as possible to reduce power consumption, but short enough to get good SNR in the whole range.
Choosing a high number of
:attr:`~acconeer.exptool.a121.algo.presence._detector.DetectorConfig.hwaas`
will increase SNR. However, it will also affect the power consumption. Choose the highest possible HWAAS that still fulfills your power requirements. A good starting point is to use the deault value.
For better use of the intra-frame presence detector, increase the number of
:attr:`~acconeer.exptool.a121.algo.presence._detector.DetectorConfig.sweeps_per_frame`.
This will improve the sensitivity.

Tuning the detector parameters
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
To adjust overall sensitivity, the easiest way is to change the thresholds.
There are separate thresholds for the inter-frame and the intra-frame parts,
:attr:`~acconeer.exptool.a121.algo.presence._detector.DetectorConfig.inter_detection_threshold`
and
:attr:`~acconeer.exptool.a121.algo.presence._detector.DetectorConfig.intra_detection_threshold`.
If only one of the motion types is of interest, the intra-frame and inter-frame presence can be run separately, otherwise they can be run together. The detection types are enabled with the
:attr:`~acconeer.exptool.a121.algo.presence._detector.DetectorConfig.inter_enable`
and
:attr:`~acconeer.exptool.a121.algo.presence._detector.DetectorConfig.intra_enable`
parameters.

For slow motion detection, there is the possibility to use
:attr:`~acconeer.exptool.a121.algo.presence._detector.DetectorConfig.inter_phase_boost`
to increase sensitivity.
This will increase detection for someone sitting still and breathing, even if the sensor is not placed in an optimal position.
However, have in mind that it will increase detection of all slow moving objects.

If a stable detection and fast loss of detection is important, for example when a person is leaving the sensor coverage, the
:attr:`~acconeer.exptool.a121.algo.presence._detector.DetectorConfig.inter_frame_presence_timeout`
functionality can be enabled.
If the inter-frame presence score has declined during a complete timeout period, the score is scaled down to get below the threshold faster.

Advanced detector parameters
^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Antoher way to adjust overall sensitivity is to change the output time constants.
Increase time constants to get a more stable output or decrease for faster response.

Fast motions - looking for a person walking towards or away from the sensor
   The intra-frame part has two parameters:
   :attr:`~acconeer.exptool.a121.algo.presence._detector.DetectorConfig.intra_frame_time_const`
   and
   :attr:`~acconeer.exptool.a121.algo.presence._detector.DetectorConfig.intra_output_time_const`.

   Look at the depthwise presence plot in the GUI. If it can’t keep up with the movements, try decreasing the intra frame time constant. Instead, if it flickers too much, try increasing the time constant.
   Furthermore, if the presence score output flickers too much, try increasing the intra output time constant, while on the other hand decreasing it will give faster detection.

Slow motions - looking for a person resting on a sofa
   For the base functionality, the inter-frame part has four parameters:
   :attr:`~acconeer.exptool.a121.algo.presence._detector.DetectorConfig.inter_frame_slow_cutoff`,
   :attr:`~acconeer.exptool.a121.algo.presence._detector.DetectorConfig.inter_frame_fast_cutoff`,
   :attr:`~acconeer.exptool.a121.algo.presence._detector.DetectorConfig.inter_frame_deviation_time_const`,
   and
   :attr:`~acconeer.exptool.a121.algo.presence._detector.DetectorConfig.inter_output_time_const`.

   The inter-frame slow cutoff frequency determines the lower frequency cutoff in the filtering. If it is set too low, unnecessary noise might be included, which gives a higher noise floor, thus decreasing sensitivity.
   On the other hand, if it is set too high, some very slow motions might not be detected.

   The inter-frame fast cutoff frequency determines the higher bound of the frequency filtering. If it is set too low, some faster motions might not be detected. However, if it is set too high, unnecessary noise might be included.
   Values larger than half the
   :attr:`~acconeer.exptool.a121.algo.presence._detector.DetectorConfig.frame_rate`
   disables this filter. If that is not enough, you need a higher frame rate or to use the intra-frame part.

Inter-frame phase boost
   To increase detection of very slow motions
   :attr:`~acconeer.exptool.a121.algo.presence._detector.DetectorConfig.inter_phase_boost`
   can be enabled.

Inter-frame timeout
   For faster loss of detection,
   :attr:`~acconeer.exptool.a121.algo.presence._detector.DetectorConfig.inter_frame_presence_timeout`
   can be used. This regulates the number of seconds needed with decreasing inter-frame presence score before the score starts to get scaled down faster.
   If set to low, the score might drop when a person sits still and breathes slowly. If set very high, it will have no effect.

Detailed description
--------------------
The sparse IQ service service returns data frames in the form of :math:`N_s` sweeps, each consisting of :math:`N_d` range distance points, see :ref:`handbook-a121-spf`.
We denote frames captured using the sparse IQ service as :math:`x(f,s,d)`, where :math:`f` denotes the frame index, :math:`s` the sweep index and :math:`d` the range distance index.

Intra-frame detection basis
^^^^^^^^^^^^^^^^^^^^^^^^^^^

For very fast motions and fast detection we have the intra-frame presence detection.
The idea is simple -- for every frame we depthwise take the deviation from the sweep mean and low pass (smoothing) filter it.

Let :math:`N_s` denote the number of sweeps, and let the deviation from the mean be:

.. math::
   s_\text{intra_dev}(f, d) = \sqrt{\frac{N_s}{N_s - 1}} \cdot \frac{1}{N_s} \sum_s |x(f, s, d) - y(f, d)|

where the first factor is a correction for the limited number of samples (sweeps).

Then, let the low pass filtered (smoothened) version be:

.. math::
   \bar{s}_\text{intra_dev}(f, d) = \alpha_\text{intra_dev} \cdot \bar{s}_\text{intra_dev}(f-1, d) + (1 - \alpha_\text{intra_dev}) \cdot s_\text{intra_dev}(f, d)

The smoothing factor :math:`\alpha_\text{intra}` is set through the
:attr:`~acconeer.exptool.a121.algo.presence._detector.DetectorConfig.intra_frame_time_const`
parameter.

The relationship between time constant and smoothing factor is described under :ref:`smoothing-factors`.

The intra-frame deviation is normalized with a noise estimate and, when appropriate, a depth filter is applied, both are discussed in later sections.

Inter-frame detection basis
^^^^^^^^^^^^^^^^^^^^^^^^^^^

In the typical case, the time between *frames* is far greater than the time between *sweeps*. Typically, the frame rate is 2 - 100 Hz while the sweep rate is 3 - 30 kHz.
Therefore, when looking for slow movements in presence, the sweeps in a frame can be regarded as being sampled at the same point in time.
This allows us to take the mean value over all sweeps in a frame, without losing any information.
In the basic part of the inter frame presence, we only use the amplitude value.
Let the *absolute mean sweep* be denoted as

.. math::
   y(f, d) = |\frac{1}{N_s} \sum_s x(f, s, d)|

We take the mean sweep :math:`y` and depthwise run it though two `exponential smoothing` filters (first order IIR low pass filters).
One slower filter with a larger smoothing factor, and one faster filter with a smaller smoothing factor.
Let :math:`\alpha_\text{fast}` and :math:`\alpha_\text{slow}` be the smoothing factors and :math:`\bar{y}_\text{fast}` and :math:`\bar{y}_\text{slow}` be the filtered sweep means.
For every depth :math:`d` in every new frame :math:`f`:

.. math::
   \bar{y}_\text{slow}(f, d) = \alpha_\text{slow} \cdot \bar{y}_\text{slow}(f-1, d) + (1 - \alpha_\text{slow}) \cdot y(f, d)

   \bar{y}_\text{fast}(f, d) = \alpha_\text{fast} \cdot \bar{y}_\text{fast}(f-1, d) + (1 - \alpha_\text{fast}) \cdot y(f, d)

The relationship between cutoff frequency and smoothing factor is described under :ref:`smoothing-factors`.

From the fast and slow filtered absolute sweep means, a deviation metric :math:`s_\text{inter_dev}` is obtained by taking the absolute deviation between the two:

.. math::
   s_\text{inter_dev}(f, d) = \sqrt{N_s} \cdot |\bar{y}_\text{fast}(f, d) - \bar{y}_\text{slow}(f, d)|

Where :math:`\sqrt{N_s}` is a normalization constant.
In other words, :math:`s_\text{inter_dev}` relates to the instantaneous power of a bandpass filtered version of :math:`y`. This metric is then filtered again with a smoothing factor, :math:`\alpha_\text{inter_dev}`, set through the
:attr:`~acconeer.exptool.a121.algo.presence._detector.DetectorConfig.inter_frame_deviation_time_const`
parameter,
to get a more stable metric:

.. math::
   \bar{s}_\text{inter_dev}(f, d) = \alpha_\text{inter_dev} \cdot \bar{s}_\text{inter_dev}(f-1, d) + (1 - \alpha_\text{inter_dev}) \cdot s_\text{inter_dev}(f, d)

This is the basis of the inter-frame presence detection.
As with the intra-fram deviation, it's favorable to normalize this with the noise floor and, if relevant, apply a depth filter. Both are discussed in later sections.

Inter-frame phase boost
^^^^^^^^^^^^^^^^^^^^^^^

To increase detection of very slow motions, we utlize the phase information in the Sparse IQ data.
The first step is to calculate the phase shift over time.
Let :math:`u(f, d)` be the *mean sweep*:

.. math::
   u(f, d) = \frac{1}{N_s} \sum_s x(f, s, d)

The mean sweep is low pass filtered and the smoothing factor, :math:`\alpha_\text{for_phase}`, is set from a fixed and quite high time constant, :math:`\tau_{for_phase}`, of 5 s:

.. math::
   \bar{u}_\text{for_phase}(f, d) = \alpha_\text{for_phase} \cdot \bar{u}_\text{for_phase}(f-1, d) + (1 - \alpha_\text{for_phase}) \cdot u(f, d)

When a new frame is sampled, we take the mean sweep and calculate the phase shift between this mean sweep and the previous low pass filtered mean sweep.
We define the phase shift to never exceed :math:`\pi` radians by adding :math:`2\pi k` for some integer :math:`k`:

.. math::
   \phi(f, d) = |angle(u(f, d)) - angle(\bar{u}_\text{for_phase}(f, d)) + 2\pi k|

In open air where only noise is measured, the phase will jump around. To amplify the phase shift boost for human breathing, while at the same time decreasing it for open air, the phase shift is weighted with the amplitude.
For a more stable weighting, the mean sweep is low pass filtered before the amplitude is calculated:

.. math::
   \bar{u}_\text{for_amp}(f, d) = \alpha_\text{inter_dev} \cdot \bar{u}_\text{for_amp}(f-1, d) + (1 - \alpha_\text{inter_dev}) \cdot u(f, d)

.. math::
   A(f, d) = |\bar{u}_\text{for_amp}(f, d)|

The amplitude is noise normalized(see next section) and truncated to reduce unwanted detections from very strong static objects:

.. math::
   A(f, d) = \max(A(f, d), 15)

Before the final output is generated, the depthwise inter-frame presence score is multiplied with the phase and amplitude weight:

.. math::
   \bar{s}_\text{inter_dev}(f, d) = \bar{s}_\text{inter_dev}(f, d) \cdot \phi(f, d) \cdot A(f, d)

Noise estimation
^^^^^^^^^^^^^^^^

To normalize detection levels, we need an estimate of the noise power generated by the sensor.
We assume that from a static channel, i.e., a radar signal with no moving reflections, the noise is white and its power is its variance.
However, we do not want to rely on having such a measurement to obtain this estimate.

Since we're looking for motions generated by humans and other living things, we know that we typically won't see fast moving objects in the data.
In other words, we may assume that *high frequency content in the data originates from sensor noise*.
Since we have a relatively high sweep rate, we may take advantage of this to measure high frequency content.

Extracting the high frequency content from the data can be done in numerous ways.
The simplest to implement is possibly a FFT, but it is computationally expensive. Instead, we use another technique which is both robust and cheap.

First, to remove any trends from fast motion in the frame, we differentiate over the sweeps :math:`N_\text{diff}=3` times:

.. math::
   x'(f, s, d) = x^{(1)}(f, s, d) = x(f, s, d) - x(f, s - 1, d)

.. math::
   ...

.. math::
   x^{(N_\text{diff})}(f, s, d) = x^{(N_\text{diff} - 1)}(f, s, d) - x^{(N_\text{diff} - 1)}(f, s - 1, d)


Then, take the mean absolute deviation:

.. math::
   \hat{n}(f, d) = \frac{1}{N_s - N_\text{diff}} \sum_{s=1 + N_\text{diff}}^{N_s} | x^{(N_\text{diff})}(f, s, d) |

And normalize such that the expectation value would be the same as if no differentiation was applied:

.. math::
   n(f, d) = \hat{n}(f, d)
   \cdot
   \left[
       \sum_{k=0}^{N_\text{diff}} \binom{N_\text{diff}}{k}^2
   \right]^{-1/2}

Finally, apply an exponential smoothing filter with a smoothing factor :math:`\alpha_\text{noise}` to get a more stable metric:

.. math::
   \bar{n}(f, d) = \alpha_\text{noise} \cdot \bar{n}(f-1, d) + (1 - \alpha_\text{noise}) \cdot n(f, d)

This smoothing factor is set from a fixed time constant of 10 s.

Both the intra-frame deviation, :math:`\bar{s}_\text{intra_dev}(f, d)`, and the inter-frame deviation, :math:`\bar{s}_\text{inter_dev}(f, d)`, as well as the amplitude in the ínter-frame phase boost is normalized by the noise estimate, :math:`\bar{n}(f, d)`, as:

.. math::
   \bar{s}(f, d) = \frac{
      \bar{s}(f, d)
   }{
      \bar{n}(f, d)
   }

Depth filtering
^^^^^^^^^^^^^^^

If we choose profile and step length in a way that the reflection spans several depth points, we apply a small depth filter with lengt :math:`n` on both the noise normalized intra-frame deviation,
and the noise normalized inter-frame deviation as:

.. math::
   z(f, d) = \frac{1}{n} \sum_{i=-1}^{1} \bar{s}(f, d + i)

where the signal :math:`\bar{s}` is zero-padded, i.e.:

.. math::
   \bar{s}(f, d) = 0 \text{ for } d < 1 \text{ and } d > N_d

Output and distance estimation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The outputs from the noise normalized and depth filtered intra-frame deviation and inter-frame deviation are the maximum scores of the respective deviation:

.. math::
   v(f) = \max_d(z(f, d))

As a final step, the outputs are low pass filtered:

.. math::
   \bar{v}(f) = \alpha_\text{output} \cdot \bar{v}(f-1) + (1 - \alpha_\text{output}) \cdot v(f)

The smooting factors for the outputs are set through the
:attr:`~acconeer.exptool.a121.algo.presence._detector.DetectorConfig.intra_output_time_const`
and the
:attr:`~acconeer.exptool.a121.algo.presence._detector.DetectorConfig.inter_output_time_const`
parameters.

When both detectors are enabled, presence is defined as either the intra-frame or the inter-frame being over the threshold.
If both have detection, the faster nature of intra-frame presence compared to inter-fram presence makes it best practise to use this score to estimate distance.
If only one part has detection we will use this for the distance estimate.
The estimate is based on the peak value in the data. Let :math:`p` be the "present"/"not present" output and :math:`d_p` be the presence depth index output:

.. math::
   p = v > v_\text{threshold}

.. math::
   d_p = \arg\max_d(z(f, d))

Inter-frame timeout
^^^^^^^^^^^^^^^^^^^
For faster decline of the inter-frame presence score, an exponential scaling of the score starts after :math:`t` seconds determined by the
:attr:`~acconeer.exptool.a121.algo.presence._detector.DetectorConfig.inter_frame_presence_timeout`
parameter. We track the number of frames with declining score, :math:`n`. With the fram rate defined as :math:`f_f`, the scale factor, :math:`C_\text{inter}`, is calculated as:

.. math::
   C_\text{inter} = \exp\left(\frac{\max(n - (t \cdot f_f), 0)}{t \cdot f_f}\right)

And the inter-frame presence score is scaled as:

.. math::
   \bar{v}_\text{inter}(f) = \frac{\bar{v}_\text{inter}(f)}{C_\text{inter}}

To reduce the effect of the inter-frame phase boost when the score is scaled, the time constant, :math:`\tau_\text{for_phase}`, controlling the smoothing factor :math:`\alpha_\text{for_phase}`, is scaled in a similar way.
With scale factor :math:`C_\tau`, the time constant, :math:`\tau_\text{scaled}`, is calculated as:

.. math::
   C_\tau = \exp\left(\frac{\max(n - (t \cdot f_f), 0) \cdot \tau_\text{for_phase}}{t}\right)

.. math::
   \tau_\text{scaled} = \frac{\tau_\text{for_phase}}{C_\tau}

.. _smoothing-factors:

Calculating smoothing factors
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

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

Configuration parameters
------------------------

.. autoclass:: acconeer.exptool.a121.algo.presence._detector.DetectorConfig
   :members:
