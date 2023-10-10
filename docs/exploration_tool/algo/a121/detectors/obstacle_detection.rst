.. _exploration_tool-a121-obstacle_detection:

Obstacle detection
==================

Introduction
------------

The purpose of the Obstacle detector is to detect objects and estimate their distance and angle from a moving platform, such as a robot.
The algorithm is built on top of the Sparse IQ service and has various configuration parameters available to tailor the detector to specific use cases.

The detector can be seen as a combination of the :doc:`Distance Detector</exploration_tool/algo/a121/detectors/distance_detection>` and :doc:`Speed Detector</exploration_tool/algo/a121/detectors/speed_detection>` to measure both the distance to and speed of an object simultaneously.

The detector utilizes the following key concepts:

**1. Distance filtering:**
A matched filter is applied along the distance dimension to improve the signal quality and suppress noise. For a more in-depth discussion on the topic of distance filter, see the :doc:`Distance Detector documentation</exploration_tool/algo/a121/detectors/distance_detection>`.

**2. DFT in the sweep dimension:**
The velocity component at every distance point is computed by performing a Discrete Fourier Transform (DFT) in the sweep dimension of the data frame. For a more in-depth discussion on the topic of speed estimation by DFT in the sweep dimension, see the :doc:`Speed Detector documentation</exploration_tool/algo/a121/detectors/speed_detection>`.

**3. Comparing frame to a threshold:**
Peaks in the distance-velocity frames, corresponding to objects in front of the radar, are found and compared to a threshold.

**4. Velocity to angle conversion:**
The A121 radar has only a single channel, and therefore cannot supply any angular information to an object. However, if the robot, and therefore also the radar, is moving at a known speed, angular information can be extracted. For example, if the radar is moving at 20 cm/s, and sees an object approaching the radar at 20 cm/s, the object is likely straight in front of the radar. If the object is instead standing still, it is likely 90 degrees to the side. More precisely,

.. math::
    :label:

    \alpha = \cos^{-1}\left(\frac{v_{object}}{v_{robot}}\right),

where :math:`\alpha` is the angle to the object, :math:`v_{object}` is the speed of the object measured by the radar and :math:`v_{robot}` is the speed of the robot or radar.

This multiple sweep angle estimation using a moving radar can be seen as `Synthetic Aperture Radar (SAR) processing
<https://en.wikipedia.org/wiki/Synthetic-aperture_radar>`_.


A121 Improvements
-----------------

If you are familiar with the :doc:`A111 Obstacle detection</exploration_tool/algo/a111/obstacle>`, a list of improvements with the A121 Obstacle detector is given here:

**1. Multiple sweeps per frame:**
A high robot speed requires a high sweep rate to determine the object angle. In the A111, each sweep needs to be transferred from the sensor before the next can be measured, which limits the maximum sweep rate. In A121, multiple sweeps can be measured in a frame, before the frame is transferred to the host. This enables higher sweep rates and therefore higher robot speeds.

**2. Subsweeps and step length:**
By utilizing subsweeps, the detector scanning range can be split up in a range close to the sensor where a low profile and low step length can be used, and a range far from the sensor where a higher profile can be used for maximum sensitivity. Note, currently the Obstacle detector in the Exploration Tool GUI does not support subsweeps, please run the example file described below.

**3. Temperature sensor:**
The surrounding temperature impacts the amplitude of the measured signal and noise. With the temperature sensor integrated in the radar, the thresholds can be adjusted when the temperature changes to keep the false alarm rate of the detector low and sensitivity high.

**4. Better distance performance:**
The A121 Obstacle Detector uses data supplied by the Sparse IQ service which has improved distance accuracy compared to the A111 IQ data service. This improved distance accuracy enables the use of bilateration with two radar sensors mounted only a few centimeters apart. Bilateration provides even more angular information. Please see the Example application :doc:`Obstacle bilateration</exploration_tool/algo/a121/examples/obstacle_bilateration>` for an example.


Limitations
-----------

- Angle estimation only works for static objects. The angle to a moving pet, human or other robot will be incorrect.
- Angle estimation is only possible if the radar is moving and the correct velocity is supplied to detector algorithm. An error in the robot velocity will lead to an error in the estimated angle.
- The angle supplied by the detector is the angle between the direction of motion of the radar and the direction from the radar to the object. If, for example, an object is found at 30 degrees, it can be 30 degrees to the left or right, and even 30 degrees up or down. One approach to circumvent this limitation is to use two radar sensors and bilateration processing, see :doc:`Obstacle bilateration</exploration_tool/algo/a121/examples/obstacle_bilateration>`.

Calibration and Threshold
-------------------------

To determine if any objects are present, the measured signal is compared to a threshold. The threshold is based on measurements collected during detector calibration.

Any signals from static objects are located in the zeroth bin after the DFT so the threshold in this bin is a constant (:attr:`~acconeer.exptool.a121.algo.obstacle._detector.DetectorConfig.num_mean_threshold`) times the mean signal from the calibration plus a constant (:attr:`~acconeer.exptool.a121.algo.obstacle._detector.DetectorConfig.num_std_threshold`) times the standard deviation. The threshold for the other DFT bins, corresponding to moving objects, is based only on the standard deviation of the signal.

During calibration, :attr:`~acconeer.exptool.a121.algo.obstacle._detector.DetectorConfig.num_frames_in_recorded_threshold` frames are collected to estimate the background for the thresholds, so it is important that no objects are present during this measurement.

A second step of the calibration step is to measure the offset compensation. The purpose of the offset compensation is to improve the distance trueness of the Obstacle detector. The compensation utilizes the loopback measurement, where the radar pulse is measured electronically on the radar, without transmitting it into the air. The location of the peak amplitude is correlated with the distance error and used to correct the distance estimate.

To trigger the calibration process in the Exploration Tool GUI, simply press the button labeled "Calibrate detector".

Subsweeps
---------
With subsweeps, the profile, HWAAS and step length can be adjusted along the range. One recommended configuration is to use a low profile in the subsweep close to the sensor to detect small obstacles in front of the robot and a higher profile and step length at larger distance to detect walls and larger objects.

The optimal subsweep configuration varies so this has to be done manually. The Obstacle Detector in the Exploration Tool GUI does not support subsweep, please see *acconeer-python-exploration/examples/algo/a121/obstacle/detector.py* for an example on running the detector with subsweeps.


Configuration parameters
------------------------
The configuration parameters of the Obstacle detector can be divided into two parts, sensor parameters and threshold parameters.

The sensor parameters are similar to the parameters used by the underlying Sparse IQ service with a few exceptions; :attr:`~acconeer.exptool.a121.algo.obstacle._detector.DetectorConfig.start_m` and :attr:`~acconeer.exptool.a121.algo.obstacle._detector.DetectorConfig.end_m` set suitable sweep range and :attr:`~acconeer.exptool.a121.algo.obstacle._detector.DetectorConfig.max_robot_speed` controls the sweep rate.

During detector calibration, :attr:`~acconeer.exptool.a121.algo.obstacle._detector.DetectorConfig.num_frames_in_recorded_threshold` of frames are collected to estimate the background signal and noise. The mean and standard deviation are then scaled with :attr:`~acconeer.exptool.a121.algo.obstacle._detector.DetectorConfig.num_mean_threshold` and :attr:`~acconeer.exptool.a121.algo.obstacle._detector.DetectorConfig.num_std_threshold` to construct a threshold.

.. autoclass:: acconeer.exptool.a121.algo.obstacle._detector.DetectorConfig
   :members:

Detector result
---------------
.. autoclass:: acconeer.exptool.a121.algo.obstacle._detector.DetectorResult
   :members:

Processor result
----------------
.. autoclass:: acconeer.exptool.a121.algo.obstacle._processors.ProcessorResult
   :members:
