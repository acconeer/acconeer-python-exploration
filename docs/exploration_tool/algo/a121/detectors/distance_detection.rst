Distance detection
==================

The goal of the distance detector is to produce highly accurate distance measurements while maintaining low power consumption by combining the features of the A121 sensor with powerful signal processing concepts, all wrapped with a simple to use API.

The full functionality can be explored in the Exploration Tool.
Once the desired performance is achieved, the configuration can be carried over to the embedded version of the algorithm, available in the C-SDK.

Introduction
------------

The purpose of the distance detector is to detect objects and estimate their distance from the sensor.
The algorithm is built on top of the Sparse IQ service and has various configuration parameters available to tailor the detector to specific use cases.
The detector utilizes the following key concepts:

**1. Distance filtering:**
A matched filter is applied along the distance dimension to improve the signal quality and suppress noise.

**2. Subsweeps:**
The measured range is split into multiple subsweeps, each configured to maintain SNR throughout the sweep while minimizing power consumption.

**3. Comparing sweep to a threshold:**
Peaks in the filtered sweep are identified by comparison to one of three available threshold methods.

**4. Estimate distance to object:**
Estimate the distance to the target by interpolation of the peak and neighboring amplitudes.

**5. Sort found peaks:**
If multiple peaks are found in a sweep, three different sorting methods can be employed, each suitable for different use-cases.

Distance filter
---------------

As the sensor produce coherent data, samples corresponding to the location of an object will have similar phase, while the phase of free-air measurements will be random.
By applying a filter in the distance domain, the noise in the free-air regions will be suppressed, resulting in an improved SNR.

The filter is automatically configured based on the detector configuration as a second order Butterworth filter with a cutoff frequency corresponding to a matched filter.

Subsweeps
---------

The measurement range is split up into multiple subsweeps to allow for optimization of power consumption and signal quality.
The profile, HWAAS and step length are automatically assigned per subsweep, based on the detector config.

- A shorter profile is selected at the start of the measurement range to minimize the interference with direct leakage, followed by longer profiles to gain SNR.
  The longest profile used can be limited by setting the parameter :attr:`~acconeer.exptool.a121.algo.distance.DetectorConfig.max_profile`.
  If no profile is specified, the subsweeps will be configured to transfer to the longest profile(without interference from direct leakage) as quickly as possible to maximize SNR.
  Longer profiles yield a higher SNR at a given power consumption level, while shorter profiles gives better depth resolution.

- The step length can also be limited by setting the parameter :attr:`~acconeer.exptool.a121.algo.distance.DetectorConfig.max_step_length`.
  If no value is supplied, the step length is automatically configured to appropriate size, maintaining good depth resolution while minimizing power consumption.
  Note, the algorithm interpolates between the measured points to maintain good resolution, even with a more coarse step length.

- HWAAS is assigned to each subsweep in order to maintain SNR throughout the measured range as the signal strength decrease with the distance between the sensor and the measured target.
  The target SNR level is adjusted using the parameter :attr:`~acconeer.exptool.a121.algo.distance.DetectorConfig.signal_quality`.

  Note, higher signal quality will increase power consumption and measurement time.

  The expected reflector shape is considered when assigning HWAAS to the subsweeps.
  For planar reflectors, such as fluid surfaces, select :attr:`~acconeer.exptool.a121.algo.distance.ReflectorShape.PLANAR`.
  For all other reflectors, select :attr:`~acconeer.exptool.a121.algo.distance.ReflectorShape.GENERIC`.

In the Exploration Tool GUI, the subsweeps can be seen as slightly overlapping lines.
If the measured object is in the overlapping region, the result from the neighboring segments is averaged together.

Thresholds
----------

To determine if any objects are present, the sweep is compared to a threshold.
A peak is defined as a middle point that has greater amplitude than its two neighbouring points.
For an object to be detected, it has to yield a peak where all three points are above the threshold.
Three different thresholds can be employed, each suitable for different use-cases.

Fixed amplitude threshold
    The simplest approach to setting the threshold is choosing a fixed threshold over the full range.
    The amplitude value is set through the parameter :attr:`~acconeer.exptool.a121.algo.distance.DetectorConfig.fixed_threshold_value`.
    The fixed amplitude threshold does not have any temperature compensation built in.
Fixed strength threshold
    This threshold takes a fixed strength value and converts to the corresponding amplitude value.
    The purpose is to produce a threshold that is able to detect an object of a with a specific reflectiveness, independent of the distance to the object.
    The strength value is set through the parameter :attr:`~acconeer.exptool.a121.algo.distance.DetectorConfig.fixed_strength_threshold_value`.
    The fixed strength threshold does not have any temperature compensation built in.
Recorded threshold
    In situations where stationary objects are present, the background signal is not flat.
    To isolate objects of interest, the threshold is based on measurements of the static environment.
    The first step is to collect multiple sweeps, from which the mean sweep and standard deviation is calculated.
    Secondly, the threshold is formed by adding a number of standard deviations (the number is determined by the parameter :attr:`~acconeer.exptool.a121.algo.distance.DetectorConfig.threshold_sensitivity`) to the mean sweep.
    The recorded threshold has a built in temperature compensation, based on the internal temperature sensor.
Constant False Alarm Rate (CFAR) threshold (default)
    A final method to construct a threshold for a certain distance is to use the signal from neighbouring distances of the same sweep.
    This requires that the object gives rise to a single strong peak, such as a fluid surface and not, for example, the level in a large waste container.
    The main advantage is that the memory consumption is minimal.
    The sensitivity of the threshold is controlled through :attr:`~acconeer.exptool.a121.algo.distance.DetectorConfig.threshold_sensitivity`.
    As the CFAR threshold is formed based on each momentary sweep, any temperature effects on the signal are implicitly accounted for by the algorithm.

Reflector shape
---------------

The expected reflector shape is considered when assigning HWAAS to the subsweeps and during peak sorting.

The reflector shape is set through the detector configuration parameter
:attr:`~acconeer.exptool.a121.algo.distance.DetectorConfig.reflector_shape`.

For a planar reflector, such as a fluid surface, select :attr:`~acconeer.exptool.a121.algo.distance.ReflectorShape.PLANAR`.
For all other reflectors, select :attr:`~acconeer.exptool.a121.algo.distance.ReflectorShape.GENERIC`.

Reflector strength
------------------

The reflector strength characterize the reflectiveness of the detected object.
The detector reports a strength number for each estimated distance.

The strength is estimated using the RLG equation, peak amplitude, noise floor estimate and the sensor base RLG.
More information on the RLG equation and base RLG can be found :ref:`here<handbook-a121-fom-rlg>`.

The estimated strength is used by the detector when sorting the estimated distances according to their relative strengths.
It can also be used by the application to infer information about a certain distance estimate.
For example, a highly reflective object such as a metal surface will typically have a higher strength number than a less reflective surface such as a wooden structure.

Ideally, the strength estimate is agnostic to the distance of the object.
However, due to close range effects, the strength tends to be under estimated at short distances (< 1m).

The strength is reported in dB.

Peak sorting
------------

Multiple objects in the scene will give rise to several peaks.
Peak sorting allows selection of which peak is of highest importance.

The peak sorting strategy is set through :attr:`~acconeer.exptool.a121.algo.distance.PeakSortingMethod`,
which is part of the detector configuration.

The following peak sorting options are available.

Closest
    This method sorts the peaks according to distance from the sensor.
Strongest (default)
    This method sorts the peaks according to their relative strength.

    Note, the reflector shape is considered when calculating each peak's strength.
    The reflector shape is selected through detector configuration parameter
    :attr:`~acconeer.exptool.a121.algo.distance.DetectorConfig.reflector_shape`.

Note, regardless of selected peak sorting strategy, all peaks and the corresponding  strenghts are returned by the distance detector.

Detector calibration
--------------------

For optimal performance, the detector performs a number of calibration steps.
The following section outlines the purpose and process of each step.
Note, which of the following calibration procedures to perform is determined by the user provided
detector config.
For instance, the close range measurement is only performed when measuring close
to the sensor.

To trigger the calibration process in the Exploration Tool gui, simply press the button labeled "Calibrate
detector".
If you are running the detector from a script, the calibration is performed by calling
the method :attr:`~acconeer.exptool.a121.algo.distance._detector.Detector.calibrate_detector`.

Noise level estimation
    The noise level is estimated by disabling of the transmitting antenna and just sample the background noise with the receiving antenna.
    The estimate is used by the algorithm for various purposes when forming thresholds and estimating strengths.

Offset compensation
    The purpose of the offset compensation is to improve the distance trueness(average error) of the distance detector.
    The compensation utilize the loopback measurement, where the pulse is measured electronically on the chip, without transmitting it into the air.
    The location of the peak amplitude is correlated with the distance error and used to correct the distance raw estimate.

Close range measurement calibration
    Measuring the distance to objects close to the sensor is challenging due to the presence of strong direct leakage.
    One way to get around this is to characterize the leakage component and then subtract it from each measurement to isolate the signal component.
    This is exactly what the close range calibration does.
    While performing the calibration, it is important that the sensor is installed in its intended geometry and that there is no object in front of the sensor as this would interfer with the direct leakage.

    Note, this calibration is only performed if close range measurement is active, given by the configured starting point.

Recorded threshold
    The recorded threshold is also recorded as a part of the detector calibration.
    Note, this calibration is only performed if the detector is configured to used recorded threshold or if close range measurement is active, where recorded threshold is used.

Detector recalibration
----------------------

To maintain optimal performance, the sensor should be recalibrated if
:attr:`~acconeer.exptool.a121.algo.distance._detector.DetectorResult.sensor_calibration_needed`
is set to True.
A sensor calibration should be followed by a detector recalibration, performed by calling :attr:`~acconeer.exptool.a121.algo.distance._detector.Detector.recalibrate_detector`.

The detector recalibration carries out a subset of the calibration steps.
All the calibration steps performed are agnostic to its surroundings and can be done at any time without considerations to the environment.

Temperature compensation (Recorded threshold)
---------------------------------------------

The surrounding temperature impacts the amplitude of the measured signal and noise.
To compensate for these effects, the recorded threshold has a built in compensation model, based on a temperature measurement, internal to the sensor.
Note, the effectiveness of the compensation is limited when measuring in the close range region.

The CFAR threshold exhibits an indirect temperature compensation as the threshold is formed based on the sweep itself.
As the sweep changes with temperature, so does the threshold accordingly.

The fixed thresholds(amplitude and strength) does not have any temperature compensation.

Result
------
The result return by the distance detector is contained in the class :attr:`~acconeer.exptool.a121.algo.distance._detector.DetectorResult`.

The two main components of the distance detector result are the estimated :attr:`~acconeer.exptool.a121.algo.distance._detector.DetectorResult.distances` and their corresponding estimated reflective :attr:`~acconeer.exptool.a121.algo.distance._detector.DetectorResult.strengths`.
The distances and the corresponding strengths are sorted according to the selected peak sorting strategy.

In addition to the distances and strengths, the result also contains the boolean :attr:`~acconeer.exptool.a121.algo.distance._detector.DetectorResult.near_edge_status`.
It indicates if an object is located close to start of the measurement range, but not resulting in a clear peak, but rather the tail of an envelope.
The purpose of the boolean is to provide information in the case when an object is present, just outside of the measurement range.
One example of when this becomes useful is the :doc:`Tank reference application</exploration_tool/algo/a121/ref_apps/tank_level>`, which is built on top of the distance detector.
If the tank is overflowing, the peak might end up just outside of the measured interval, but the tail end of the envelope would still be observable.

The result also contains the boolean :attr:`~acconeer.exptool.a121.algo.distance._detector.DetectorResult.sensor_calibration_needed`.
If True, the procedure, described in the section Detector Recalibration, needs to be performed to maintain optimal performance.

Note, the sweep and threshold, presented in the distance detector GUI are not returned by the distance detector.
These entities are processed and evaluated internally to the algorithm.
The purpose of visualizing them in the GUI is to guide in the process of determining the detector configuration, such as selection of threshold strategy and sensitivity.

Configuration parameters
------------------------

.. autoclass:: acconeer.exptool.a121.algo.distance.DetectorConfig
   :members:

.. autoclass:: acconeer.exptool.a121.algo.distance.ThresholdMethod
    :members:
    :undoc-members:

.. autoclass:: acconeer.exptool.a121.algo.distance.PeakSortingMethod
    :members:
    :undoc-members:

.. autoclass:: acconeer.exptool.a121.algo.distance.ReflectorShape
    :members:
    :undoc-members:

Detector calibration
--------------------

.. autoclass:: acconeer.exptool.a121.algo.distance._detector.Detector.calibrate_detector
   :members:

.. autoclass:: acconeer.exptool.a121.algo.distance._detector.Detector.recalibrate_detector
   :members:


Detector result
---------------
.. autoclass:: acconeer.exptool.a121.algo.distance._detector.DetectorResult
   :members:
