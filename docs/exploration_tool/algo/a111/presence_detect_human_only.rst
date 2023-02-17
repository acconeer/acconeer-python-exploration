.. _human-only-presence-detection:

Presence detection human only
=============================

This presence detector was generated from  :ref:`sparse-presence-detection`. The purpose of this version of presence detector is to remove false detections created from non-human moving objects such as fans, plants, curtains and other possible objects in a small room. This presence detector works by comparing the fast motion score and slow motion score.
Our investigation shows that the human creates high spikes in both fast and slow motion score, while moving objects create high spikes in slow motion score only. The key concepts for this presence detector are:

   - Comparing the fast and slow motion score to individually set thresholds
   - Implementation of adaptive threshold using fast motion guard interval
   - Implementation of fast motion outlier detection for quiet room (e.g. meeting room)

Slow motion and fast motion
^^^^^^^^^^^^^^^^^^^^^^^^^^^
Below is an example of the detections of both fast and slow motions. It is measured in a room with size of approximately 3 x 3 x 3 m. The following events are:

   1. 0-80 seconds is empty room
   2. 80-100 seconds is people coming, installing and turning on a fan
   3. 100-250 seconds is empty room with a fan turned on

.. _figure_presence_human_only_1:

.. figure:: /_static/processing/presence_human_only_1.png
    :align: center

    A measurement with multiple cases of human and fan presence

The :numref:`figure_presence_human_only_1` can not be seen directly in exploration tool GUI, but was used in the algorithm development. From this we conclude:

   - The inter/slow motion is measuring human presence from, e.g., breathing
   - The intra/fast motion is measuring bigger movements from the human body

Fast motion score, :math:`s_\text{fast}(f)`, and slow motion score, :math:`s_\text{slow}(f)`, are calculated from the :math:`\bar{s}_\text{fast}(f, d)` and :math:`\bar{s}_\text{slow}(f, d)` by taking the maximum value over the distances. The :math:`\bar{s}_\text{fast}(f, d)` that is :math:`\bar{s}_\text{intra}(f, d)` and the :math:`\bar{s}_\text{slow}(f, d)` that is :math:`\bar{s}_\text{inter}(f, d)` are processed from the :ref:`sparse-presence-detection` processor. The motion scores are then compared to fast motion threshold, :math:`v_f`, and slow motion threshold, :math:`v_s`, to obtain fast motion detection, :math:`p_f`, and slow motion detection, :math:`p_s`. Lastly, the decision of presence detected, :math:`p`, is defined as either fast motion detection or slow motion detection.

.. math::
   s_\text{fast}(f) = \max_d(\bar{s}_\text{fast}(f, d))

.. math::
   s_\text{slow}(f) = \max_d(\bar{s}_\text{slow}(f, d))

.. math::
   p_f = s_\text{fast} > v_f

.. math::
   p_s = s_\text{slow} > v_s

.. math::
   p = p_f \text{ or } p_s

Adaptive threshold
^^^^^^^^^^^^^^^^^^
Adaptive threshold is one of the configurations to remove false detections created by fans, plants, and curtains. As mentioned before, those objects creates mainly slow motions. The adaptive threshold works by recording the maximum value of slow motion score for each distance during a recording time. We use these recorded values as a new threshold for each distance with the expectation that the recorded slow motion scores are the highest slow motion values created by the non-human objects. It is expected not to have fast motion detection during the recording time.
For this implementation to work, there are three main timelines as shown in the :numref:`figure_presence_human_only_2`. This picture can not be seen directly in exploration tool GUI, but was used in the algorithm development.

   A. A person was inside of the room or inside the sensor coverage. The fluctuations of slow motion score will not be recorded because of the fast motion detection. The recording time will start when there is no fast motion.
   B. The room is empty, but slow motion score has not settled due to the low pass filtering in the presence detector. The slow motion score will not be recorded. This time window, :math:`w_h`, is dependent on the the :attr:`~acconeer.exptool.a111.algo.presence_detect_human_only.ProcessingConfiguration.slow_motion_deviation_time_const`, :math:`\tau`.
   C. The last time window, :math:`w_\text{cal}`, is the actual recording step of the  slow motion score, which later will be set as a new threshold. The B and C time windows are combined in the :math:`w_g`, controlled by the :attr:`~acconeer.exptool.a111.algo.presence_detect_human_only.ProcessingConfiguration.fast_guard_s`. We have the following:

.. math::
   w_h = 5 \cdot \tau

.. math::
   w_\text{cal} = w_g - w_h

.. _figure_presence_human_only_2:

.. figure:: /_static/processing/presence_human_only_2.png
    :align: center

    Implementation of :attr:`~acconeer.exptool.a111.algo.presence_detect_human_only.ProcessingConfiguration.adaptive_threshold`

The non-human object, can in some cases create motion that will be detected as presence. The false detections, such as false negative and false positive, marked with red circles on :numref:`figure_presence_human_only_3`, are caused by different results from slow motion detection and fast motion detection.

By activating the adaptive threshold, it will automatically change the threshold over distances to a threshold value that is higher than the measured slow motion detection. The :numref:`figure_presence_human_only_3` on the third plot represents the threshold for the case of plant in the room after fast motion guard periods completed.

.. _figure_presence_human_only_3:

.. figure:: /_static/processing/presence_human_only_3.png
    :align: center

    UI appearance

After the fast guard window, the slow motion threshold will not have equal values for all distances any longer. The slow motion detection, :math:`p_s`, is then redefined as comparing the depthwise slow motion score, :math:`\bar{s}_\text{slow}(f, d)`, to the recorded depthwise slow motion threshold :math:`\bar{v}_s(d)`.

.. math::
   p_s = \bar{s}_\text{slow}(f, d) > \bar{v}_s(d)

Fast motion outlier detection
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
In fast motion detection, humans will be detected if they create enough fast motion. If a person is sitting still, it will create a very low spike. Due to the consistency of the fast motion score, this low spike can be detected in the fast motion detection even though it is not above the threshold value. The fast motion outliers detection has the purpose of detecting this relatively short and weak fast motion. It records previous frames of fast motion score, :math:`s_\text{fast}(f)`. The recorded values are then sorted from least to greatest, :math:`\bar{u}`. The :math:`1^{st}` quartile and :math:`3^{rd}` quartile are calculated with percentile based formula. With :math:`n_s` being the number of recorded values we have:

.. math::
   s_\text{fast}(f) = \max_d(\bar{s}_\text{fast}(f, d))

.. math::
   \bar{u} = [s_\text{fast}(f_{0}), s_\text{fast}(f_{1}), ...] \text{, such that } s_\text{fast}(f_{i}) < s_\text{fast}(f_{i+1})

.. math::
   Q_1 = \frac{n_s + 1}{100} \cdot 25 \cdot \bar{u}

.. math::
   Q_3 = \frac{n_s + 1}{100} \cdot 75 \cdot \bar{u}

The interquartile range, :math:`IQR`, for fast motion score is calculated to determine the boundaries for the outlier detection. Based on our investigation, the human creates an :math:`IQR` value above 0.15, hence, the IQR is defined to never exceed this value. The lower boundary, :math:`L_b`, and the upper boundary, :math:`U_b`, are then calculated from the :math:`IQR` and the :math:`Q_\text{factor}`. The :math:`Q_\text{factor}` adjusts the boundaries and sets the sensitivity in the outlier detection. The more fluctuative fast motion score in an empty room without human is, the higher the :math:`Q_\text{factor}` should be. In our investigation, the optimal value of :math:`Q_\text{factor}` is 3 to differentiate between a human and other objects.  Finally, the fast motion detection, :math:`p_f`, will also be defined as the fast motion score being outside the boundaries.

.. math::
   IQR =
   \begin{cases}
   Q_3 - Q_1 & \text{if } Q_3 - Q_1 <0.15 \\
   0.15 & \text{otherwise} \\
   \end{cases}

.. math::
   L_b = Q_1 - Q_\text{factor} \cdot IQR

.. math::
   U_b = Q_3 + Q_\text{factor} \cdot IQR

.. math::
   p_f =
   \begin{cases}
   s_\text{fast} > U_b \text{ or } s_\text{fast} < L_b & \text{if } s_\text{fast} <= v_f \\
   s_\text{fast} > v_f & \text{otherwise}\\
   \end{cases}

.. note::
   Some configurations here in :ref:`human-only-presence-detection`, are exactly the same as in the :ref:`sparse-presence-detection` only with name adaptation.

   :attr:`~acconeer.exptool.a111.algo.presence_detect_human_only.ProcessingConfiguration.slow_motion_hf_cutoff` is the same as :attr:`~acconeer.exptool.a111.algo.presence_detection_sparse.ProcessingConfiguration.inter_frame_fast_cutoff`

   :attr:`~acconeer.exptool.a111.algo.presence_detect_human_only.ProcessingConfiguration.slow_motion_lf_cutoff` is the same as :attr:`~acconeer.exptool.a111.algo.presence_detection_sparse.ProcessingConfiguration.inter_frame_slow_cutoff`

   :attr:`~acconeer.exptool.a111.algo.presence_detect_human_only.ProcessingConfiguration.slow_motion_deviation_time_const` is the same as :attr:`~acconeer.exptool.a111.algo.presence_detection_sparse.ProcessingConfiguration.inter_frame_deviation_time_const`

   :attr:`~acconeer.exptool.a111.algo.presence_detect_human_only.ProcessingConfiguration.fast_motion_time_const` is the same as :attr:`~acconeer.exptool.a111.algo.presence_detection_sparse.ProcessingConfiguration.intra_frame_time_const`

Graphical overview
^^^^^^^^^^^^^^^^^^

.. graphviz:: /_graphs/presence_detect_human_only.dot
   :align: center

Configuration parameters
^^^^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: acconeer.exptool.a111.algo.presence_detect_human_only.ProcessingConfiguration
   :members:
