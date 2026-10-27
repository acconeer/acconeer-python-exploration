.. _a212_motion_detection:

################
Motion Detection
################

Introduction
************
The Motion Detection :term:`Example Application` for the A212 sensor detects and locates moving objects in a 3D volume in front of the sensor. The processor:

* high-pass filters the IQ data to suppress static reflectors,
* builds per-range channel covariance matrices,
* beamforms an azimuth/elevation/distance heatmap,
* applies a CFAR threshold,
* refines local maxima through interpolation,
* and returns the surviving detections as 3D Spherical peaks in the sensor frame and Cartesian peaks in the world frame.


Configuration
*************
This section describes the most important configuration parameters and how to tune them. The processor is configured with four classes: :class:`~acconeer.exptool.a2.algo.motion_detection.MotionDetectionConfig` holds the processing parameters, :class:`~acconeer.exptool.a2.algo.motion_detection.SensorInstallation` describes how the sensor is mounted, :class:`~acconeer.exptool.a2.algo.motion_detection.DetectionVolume` the region to detect within, and :class:`~acconeer.exptool.a2.algo.motion_detection.WallMountSessionAbstractionConfig` abstracts the sensor configuration settings. The fields described below are the common-case parameters exposed in the Exploration Tool GUI's main view. Advanced fields (beamformer internals, CFAR kernel shape, peak interpolation tuning, …) live behind the GUI's *Advanced* section and remain visible in the full :ref:`API listing <a212_motion_detection_api>` at the bottom of this page.


MotionDetectionConfig
=====================

The :attr:`~acconeer.exptool.a2.algo.motion_detection.MotionDetectionConfig.high_pass_filter_time_constant_s` controls the IIR high-pass filter applied to the IQ data before the covariance matrices are formed. Its purpose is to suppress static reflectors so that only the moving component reaches the beamformer. A larger value lets slower motion through but also keeps stationary reflectors visible for longer when the scene changes (e.g. a moved chair will look like presence for several seconds). A smaller value adapts faster to scene changes at the cost of suppressing slow targets. A starting range of 0–10 s works for most human-motion use cases. A value of 0 means each frame is detrended only by the mean sweep. This will suppress slow movements while passing faster movements such as walking. Setting the parameter higher will apply a detrend of a low-pass version of the mean sweep over frames. This is suitable to detect slower motions such as sitting persons that change on the timescale of :attr:`~acconeer.exptool.a2.algo.motion_detection.WallMountSessionAbstractionConfig.frame_rate`.

The :attr:`~acconeer.exptool.a2.algo.motion_detection.MotionDetectionConfig.covariance_matrix_time_constant_s` is the time constant of the IIR low-pass filter applied to the per-range channel covariance matrices. It controls how much temporal averaging the beamformer sees: larger values stabilize the beamformer, reduce beamformer variance and improve the SNR for slow motions, while smaller values track fast motion more responsively. Setting it to ``0`` disables temporal smoothing entirely and gives the highest signal strength at the cost of higher variance.

The :class:`~acconeer.exptool.a2.algo.motion_detection.DetectionVolume` defines the region in which motion is to be detected, and the sensor configuration is adapted to cover it: a box in the world frame, cut by a range and angle sector in the sensor frame. The world frame has z up and its origin at the sensor; the sensor frame has its y axis along the boresight. :attr:`~acconeer.exptool.a2.algo.motion_detection.DetectionVolume.az_angle_range` / :attr:`~acconeer.exptool.a2.algo.motion_detection.DetectionVolume.el_angle_range` set the ``(min, max)`` azimuth/elevation coverage in degrees, in the sensor frame. If needed, a :class:`~acconeer.exptool.a2.algo.motion_detection.MotionDetectionConfig` can override either axis for itself via :attr:`~acconeer.exptool.a2.algo.motion_detection.MotionDetectionConfig.az_angle_range` / :attr:`~acconeer.exptool.a2.algo.motion_detection.MotionDetectionConfig.el_angle_range` (``None``, the default, uses the detection volume's value).

The :attr:`~acconeer.exptool.a2.algo.motion_detection.DetectionVolume.x_bounds_m` / :attr:`~acconeer.exptool.a2.algo.motion_detection.DetectionVolume.y_bounds_m` are the ``(min, max)`` bounds in meters of the box, in the world frame; set them together, or neither to leave out the box. The box has no height: when sizing the range to measure, it is taken as high as the room, from the floor (:attr:`~acconeer.exptool.a2.algo.motion_detection.SensorInstallation.mount_height_m` below the sensor) up to 2.5 m above it. Peaks outside the box are dropped before being returned. The bounds are intended to suppress reflectors outside the physical room or volume to be covered (walls in front or to the side of the sensor). :attr:`~acconeer.exptool.a2.algo.motion_detection.DetectionVolume.start_m` / :attr:`~acconeer.exptool.a2.algo.motion_detection.DetectionVolume.end_m` limit the range from the sensor. Either set the box or the end, so that the volume has a farthest point; where the box and the range limits both limit the range, the stricter one applies. If needed, a :class:`~acconeer.exptool.a2.algo.motion_detection.MotionDetectionConfig` can adjust the box per axis for itself via :attr:`~acconeer.exptool.a2.algo.motion_detection.MotionDetectionConfig.detection_volume_x_bound_offset_m` / :attr:`~acconeer.exptool.a2.algo.motion_detection.MotionDetectionConfig.detection_volume_y_bound_offset_m` / :attr:`~acconeer.exptool.a2.algo.motion_detection.MotionDetectionConfig.detection_volume_z_bound_offset_m`, each a ``(lo, hi)`` offset added to the detection volume's bound for that axis, or for z to the room's height (``None`` drops the bound on that axis for this processor, as does a detection volume without a box).

The :attr:`~acconeer.exptool.a2.algo.motion_detection.MotionDetectionConfig.cfar_sensitivity` controls the detection threshold on a 0–1 scale. A higher value increases sensitivity (lower threshold, more detections, more false positives); a lower value reduces sensitivity (higher threshold, fewer detections, less false positives). Internally the value is mapped log-linearly onto a theoretical per-pixel (CA-CFAR) false-positive rate; this should be viewed as a tuning parameter and not an exact false positive rate indication since it relies on an approximate noise model.

The :attr:`~acconeer.exptool.a2.algo.motion_detection.SensorInstallation.z_rotation` is the sensor rotation about its z (boresight-perpendicular vertical) axis in degrees — a pan. Positive values follow the right-handed convention. Use it e.g. when the sensor is mounted in a corner pointing :math:`45^\circ` in relation to the wall.

The :attr:`~acconeer.exptool.a2.algo.motion_detection.SensorInstallation.x_rotation` is the sensor rotation about its x axis (tilt) in degrees. Set it to match the sensor's tilt relative to the world frame. The normal usage is to set it if the sensor is placed on a wall tilted downward.

The :attr:`~acconeer.exptool.a2.algo.motion_detection.SensorInstallation.mount_height_m` is the height of the sensor above the floor. It places the floor, from which the room is taken to be 2.5 m high.

The measured range is *derived* from the detection volume: it covers the nearest and farthest points of the box, or :attr:`~acconeer.exptool.a2.algo.motion_detection.DetectionVolume.start_m` / :attr:`~acconeer.exptool.a2.algo.motion_detection.DetectionVolume.end_m` where those are stricter. Without a box, the range limits alone set it, so tight bounds or range limits are the primary way to cut compute on the near-sensor region and to cap the far-side range.


WallMountSessionAbstractionConfig
=================================

The :attr:`~acconeer.exptool.a2.algo.motion_detection.WallMountSessionAbstractionConfig.profile` selects the pulse profile. Longer profiles trade range resolution for SNR; shorter profiles do the opposite. Since the angular resolution at the typical distances used in this processor typically corresponds to a wider footprint than the radial resolution with profile 6 there is little benefit of using shorter profiles in most applications.

The :attr:`~acconeer.exptool.a2.algo.motion_detection.WallMountSessionAbstractionConfig.frame_rate` sets the sensor's frame rate in Hz; the sensor times the frames itself. It mainly affects latency and the amount of temporal averaging that can be done at a given filter time constant. A frame rate higher than the sensor configuration can sustain is reported as a validation error.

The :attr:`~acconeer.exptool.a2.algo.motion_detection.WallMountSessionAbstractionConfig.signal_quality_db` sets the target SNR (in dB) for a 0 dBsm reflector, guaranteed everywhere in the detection volume — not just on boresight — at the :attr:`~acconeer.exptool.a2.algo.motion_detection.WallMountSessionAbstractionConfig.snr_evaluation_height_m` plane. The sensor configuration (subsweep count and per-subsweep HWAAS, up to :attr:`~acconeer.exptool.a2.algo.motion_detection.WallMountSessionAbstractionConfig.max_num_subsweeps`) needed to reach it is derived automatically, accounting for the antenna's angle-dependent gain falloff. The SNR includes the processing gain from using all 12 TX/RX channels and all sweeps within a frame. If the requested SNR cannot be reached, HWAAS saturates and a warning is shown in the GUI.

The :attr:`~acconeer.exptool.a2.algo.motion_detection.WallMountSessionAbstractionConfig.max_num_subsweeps` caps how many subsweeps the automatic layout may use. More subsweeps let HWAAS track the SNR requirement more closely across range and angle, at the cost of higher frame overhead.

The :attr:`~acconeer.exptool.a2.algo.motion_detection.WallMountSessionAbstractionConfig.snr_evaluation_height_m` is the height above the floor, in meters, of the horizontal plane at which :attr:`~acconeer.exptool.a2.algo.motion_detection.WallMountSessionAbstractionConfig.signal_quality_db` is guaranteed. It must not lie below the floor, and is at most 2.5 m, the room's height. The default, 1.2 m, is about the chest height of people in front of the sensor.


Tuning Guide
============

* Slow detection response:

    Increase :attr:`~acconeer.exptool.a2.algo.motion_detection.WallMountSessionAbstractionConfig.frame_rate`.

    Decrease :attr:`~acconeer.exptool.a2.algo.motion_detection.MotionDetectionConfig.covariance_matrix_time_constant_s`.

* False positives too frequent:

    Decrease :attr:`~acconeer.exptool.a2.algo.motion_detection.MotionDetectionConfig.cfar_sensitivity` to raise the CFAR threshold map and reject more spurious detections.


* Low detection of fast moving objects:

    Decrease :attr:`~acconeer.exptool.a2.algo.motion_detection.MotionDetectionConfig.covariance_matrix_time_constant_s` to reduce beamformer lag.

    Increase :attr:`~acconeer.exptool.a2.algo.motion_detection.WallMountSessionAbstractionConfig.frame_rate`.

* Low detection of slow moving objects:

    Increase :attr:`~acconeer.exptool.a2.algo.motion_detection.MotionDetectionConfig.high_pass_filter_time_constant_s` so that slowly moving targets are not high-pass filtered out together with the static clutter.

    Increase :attr:`~acconeer.exptool.a2.algo.motion_detection.WallMountSessionAbstractionConfig.signal_quality_db`.

    Increase :attr:`~acconeer.exptool.a2.algo.motion_detection.MotionDetectionConfig.covariance_matrix_time_constant_s`

* Static objects detected as motion:

    Decrease :attr:`~acconeer.exptool.a2.algo.motion_detection.MotionDetectionConfig.high_pass_filter_time_constant_s` for faster adaptation to changes in the static environment (e.g. moved furniture). A rule of thumb is that it takes about :math:`3 \cdot` :attr:`~acconeer.exptool.a2.algo.motion_detection.MotionDetectionConfig.high_pass_filter_time_constant_s` seconds to adapt to scene changes.

* Field of view too narrow:

    Widen :attr:`~acconeer.exptool.a2.algo.motion_detection.DetectionVolume.az_angle_range` / :attr:`~acconeer.exptool.a2.algo.motion_detection.DetectionVolume.el_angle_range` (and the x/y bounds, if they cut off those angles). The automatic subsweep layout raises HWAAS as needed to keep :attr:`~acconeer.exptool.a2.algo.motion_detection.WallMountSessionAbstractionConfig.signal_quality_db` across the whole range/angle span, at the cost of increased current consumption.


Presets
=======

Two presets share the same 5 m baseline configuration and differ only in :attr:`~acconeer.exptool.a2.algo.motion_detection.MotionDetectionConfig.high_pass_filter_time_constant_s` — pick the one matching the motion class to be detected. Each returns a (:class:`~acconeer.exptool.a2.algo.motion_detection.MotionDetectionConfig`, :class:`~acconeer.exptool.a2.algo.motion_detection.WallMountSessionAbstractionConfig`, :class:`~acconeer.exptool.a2.algo.motion_detection.SensorInstallation`, :class:`~acconeer.exptool.a2.algo.motion_detection.DetectionVolume`) tuple; call :meth:`~acconeer.exptool.a2.algo.motion_detection.WallMountSessionAbstractionConfig.get_session_config` with the :class:`~acconeer.exptool.a2.algo.motion_detection.SensorInstallation` and the :class:`~acconeer.exptool.a2.algo.motion_detection.DetectionVolume` to obtain an :class:`~acconeer.exptool.a2.SessionConfig`.

* :func:`~acconeer.exptool.a2.algo.motion_detection.get_walking_detection_configs` — for fast motion such as walking. Sets ``high_pass_filter_time_constant_s = 0.0`` (no temporal high-pass; each frame is detrended against its own mean sweep).
* :func:`~acconeer.exptool.a2.algo.motion_detection.get_sitting_detection_configs` — for slow motion such as a sitting or breathing person. Sets ``high_pass_filter_time_constant_s = 0.5`` so that slow targets are not high-pass filtered out together with the static clutter.


Physical Integration
********************
The algorithm assumes the sensor's azimuth plane is horizontal to the surface being monitored. Tilts and rotations of the physical installation are compensated by setting :attr:`~acconeer.exptool.a2.algo.motion_detection.SensorInstallation.z_rotation` (pan) and :attr:`~acconeer.exptool.a2.algo.motion_detection.SensorInstallation.x_rotation` (tilt) so that the reported Cartesian peaks (and the :attr:`~acconeer.exptool.a2.algo.motion_detection.DetectionVolume.x_bounds_m` / :attr:`~acconeer.exptool.a2.algo.motion_detection.DetectionVolume.y_bounds_m` filters) are expressed in the world frame.


Processor Output
****************
.. autoclass:: acconeer.exptool.a2.algo.motion_detection.MotionDetectionResult
   :members:
   :undoc-members:


.. _a212_motion_detection_api:

Exploration Tool Python API
***************************

.. autoclass:: acconeer.exptool.a2.algo.motion_detection.MotionDetectionConfig
   :members:
   :undoc-members:

.. autoclass:: acconeer.exptool.a2.algo.motion_detection.SensorInstallation
   :members:
   :undoc-members:

.. autoclass:: acconeer.exptool.a2.algo.motion_detection.DetectionVolume
   :members:
   :undoc-members:

.. autoclass:: acconeer.exptool.a2.algo.motion_detection.WallMountSessionAbstractionConfig
   :members:
   :undoc-members:

.. autoclass:: acconeer.exptool.a2.algo.motion_detection.MotionDetectionProcessor
   :members:
   :undoc-members:

.. autofunction:: acconeer.exptool.a2.algo.motion_detection.get_walking_detection_configs

.. autofunction:: acconeer.exptool.a2.algo.motion_detection.get_sitting_detection_configs
