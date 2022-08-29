Distance detection
==================

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

As the sensor produce coherent data, samples corresponding to the location of an object will have similar phase, while the phase of free-air measurements will be random. By applying a filter in the distance domain, the noise in the free-air regions will be suppressed, resulting in an improved SNR.

The filter is automatically configured based on the detector configuration as a second order Butterworth filter with a cutoff frequency corresponding to a matched filter.

Subsweeps
---------

The measurement range is split up into multiple subsweeps to allow for optimization of power consumption and signal quality. The profile, HWAAS and step length are automatically assigned per subsweep, based on the detector config.

- A shorter profile is selected at the start of the measurement range to minimize the interference with direct leakage, followed by longer profiles to gain SNR. The longest profile used can be limited by setting the parameter :attr:`~acconeer.exptool.a121.algo.distance._detector.DetectorConfig.max_profile`. If no profile is specified, the subsweeps will be configured to transfer to the longest profile(without interference from direct leakage) as quickly as possible to maximize SNR. Longer profiles yield a higher SNR at a given power consumtion level, while shorter profiles gives better depth resolution.

- The step length can also be limited by setting the parameter :attr:`~acconeer.exptool.a121.algo.distance._detector.DetectorConfig.max_step_length`. If no value is supplied, the step length is automatically configured to appropriate size, maintaining good depth resolution while minimizing power consumption. Note, the algorithm interpolates between the measured points to maintain good resolution, even with a more coarse step length.

- HWAAS is assigned to each subsweep in order to maintain SNR throughout the measured range as the signal strength decrease with the distance between the sensor and the measured target. The target SNR level is adjusted using the parameter :attr:`~acconeer.exptool.a121.algo.distance._detector.DetectorConfig.signal_quality`. Note, higher signal quality will increase power consumption and measurement time.

In the Exploration Tool GUI, the subsweeps can be seen as slightly overlapping lines. If the measured object is in the overlapping region, the result from the neighboring segments is averaged together.

Thresholds
----------

To determine if any objects are present, the sweep is compared to a threshold. Three different thresholds can be employed, each suitable for different use-cases.

Fixed threshold
    The simplest approach to setting the threshold is choosing a fixed threshold over the full range.
Recorded threshold
    In situations where stationary objects are present, the background signal is not flat. To isolate objects of interest, the threshold is based on measurements of the static environment. The first step is to collect multiple sweeps, from which the mean sweep and standard deviation is calculated.
    Secondly, the threshold is formed by adding a number of standard deviations (the number is determined by the parameter :attr:`~acconeer.exptool.a121.algo.distance._detector.DetectorConfig.threshold_sensitivity`) to the mean sweep.
Constant False Alarm Rate (CFAR) threshold(default)
    A final method to construct a threshold for a certain distance is to use the signal from neighbouring distances of  the same sweep. This requires that the object gives rise to a single strong peak, such as a water surface and not, for example, the level in a large waste container. The main advantage is that the memory consumption is minimal.

Peak sorting
------------

Multiple objects in the scene will give rise to several peaks. Peak sorting allows selection of which peak is of highest importance. The following options are available.

Closest
    This method returns the closest peak.
Highest RCS(default)
    This method returns the peak corresponding with the highest radar cross section according to the radar equation.

Close range measurement
-----------------------

Measuring the distance to objects close to the sensor is challenging due to the presence of strong direct leakage.
One way to get around this is to characterize the leakage component and then subtract it from each measurement to isolate the signal of interest.

The first step in doing this is to calibrate the direct leakage by calling the detector method :attr:`~acconeer.exptool.a121.algo.distance._detector.Detector.calibrate_close_range`.
In Exploration Tool, this is done by pressing *Calibrate close range*. Note, it is important that the sensor is installed in its intended geometry and
that there is no obstruction in front of the sensor while performing the close range calibration as the goal is to isolate and characterize the direct leakage.

Next, the recorded threshold is calibrated by calling the detector method :attr:`~acconeer.exptool.a121.algo.distance._detector.Detector.calibrate_recorded_threshold` or pressing *Record threshold* in the GUI. The reason for using recorded
threshold with close range measurement is to get more robust performance of the detector as the resulting sweep after subtracting the direct leakage will have some
residuals due to noise. This could trigger false detections when running CFAR or Fixed threshold, while in the case of recorded threshold, the magnitude of the residuals will be reflected in the threshold.

Temperature compensation
------------------------

The surrounding temperature impacts the amplitude of the measured signal and noise. To compensate for these effects, the recorded threshold has a built in compensation model, based on a temperature measurement, internal to the sensor. Note, the effectiveness of the compensation is limited when measuring in the close range region.

Configuration parameters
------------------------

.. autoclass:: acconeer.exptool.a121.algo.distance._detector.DetectorConfig
   :members:
