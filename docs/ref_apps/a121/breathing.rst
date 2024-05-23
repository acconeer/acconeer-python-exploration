Breathing
=========

This reference application shows how the breathing rate of a stationary person can be estimated using the A121 sensor.

The algorithm consists of the following key concepts:

- Determine the distance to the person using the presence algorithm.
- Form a time series, reflecting the breathing motion over time.
- Remove irrelevant signal content by applying a bandpass filter to the time series.
- Estimate the breathing rate by calculating the power spectrum of the time series.

Each concept is explained in more detail in the following sections.

Determine distance to person
----------------------------
The algorithm utilize the
:doc:`presence algorithm</detectors/a121/presence_detection>`
to determine the distance to the person, located somewhere in the measurement range.
The measurement range is defined through the reference application configuration parameters
:attr:`~acconeer.exptool.a121.algo.breathing._ref_app.RefAppConfig.start_m`
and :attr:`~acconeer.exptool.a121.algo.breathing._ref_app.RefAppConfig.end_m`.

The presence processor is run for a configurable duration of time, determined by
:attr:`~acconeer.exptool.a121.algo.breathing._ref_app.RefAppConfig.distance_determination_duration`.
If no presence is detected during this period, a new measurement period is initiated.
This procedure is repeated until a person is detected.

When presence is detected, the corresponding distance estimates (outputted by the presence algorithm) are passed through a lowpass filter.
The final output of the filter, after the configured duration has elapsed, is used as the distance to the person.

Once the distance to the person has been determined, a sub-segment of the measured range is analyzed to estimate the breathing rate.
The segment is centered around the estimated distance and the width is determined by the parameter
:attr:`~acconeer.exptool.a121.algo.breathing._ref_app.RefAppConfig.num_distances_to_analyze`.
The value of the parameter should be determined by evaluating the specific use case at hand.
A larger number will yield more distances being fed through the algorithm, providing more information, but also increase processing and memory usage.
Also, a too large number can potentially result in distances containing no breathing being fed to the algorithm, introducing more noise to estimation process.

The usage of the presence processor can be disabled through the user parameter
:attr:`~acconeer.exptool.a121.algo.breathing._ref_app.RefAppConfig.use_presence_processor`.
If disabled, the full measurement range is analyzed.
In this case, it is important to narrow the measured range to the interval where the breathing motion is present.

Form time series
----------------
Once the segment to be analyzed has been identified, a FIFO buffer is used to store the time series, characterizing the breathing motion at each distance in the segment.

The concept for estimating the breathing motion utilize processing, similar to what is described in the phase tracking example.
For details, see the :doc:`phase tracking documentation</example_apps/a121/phase_tracking>`.

The sparse IQ data service produce complex data samples where the amplitude corresponds to the amount of measured energy
and the phase to the relative timing of the transmitted and returning pulse.
A displacement of the reflecting object results in a change of this relative phase.
The difference in phase between two consecutive measurements can therefor be converted to the corresponding relative change in distance to the reflecting object.
The algorithm takes advantage of this by cumulating the relative changes in phase and thereby track the motion of the chest of the breathing person.

The result is stored in the previously mentioned FIFO buffer.
The length of the buffer depends on the selected time series length (:attr:`~acconeer.exptool.a121.algo.breathing._processor.BreathingProcessorConfig.time_series_length_s`),
frame rate (:attr:`~acconeer.exptool.a121.algo.breathing._ref_app.RefAppConfig.frame_rate`).
The number of buffers is determined by the number of distance to be analyzed
(:attr:`~acconeer.exptool.a121.algo.breathing._ref_app.RefAppConfig.num_distances_to_analyze`).

Bandpass filter
---------------
The purpose of the bandpass filter is to remove irrelevant content in the signal before further processing.
When configuring the application, the user specifies the lowest and highest anticipated breathing rates through the configuration parameters :attr:`~acconeer.exptool.a121.algo.breathing._processor.BreathingProcessorConfig.lowest_breathing_rate` and :attr:`~acconeer.exptool.a121.algo.breathing._processor.BreathingProcessorConfig.highest_breathing_rate`.
These values are used when defining the parameters of the bandpass filter.

After filtering, low frequency components, including bias, and high frequency components are suppressed, resulting in a more easily processed time series.

Estimate power spectrum
-----------------------
The breathing rate is estimated by identifying the peak location in the Power Spectral Density (PSD) of the time series.

As the frequency bins of the PSD are discrete, peak interpolation is utilized to further improve the estimation accuracy.

The PSD is not calculated at each time step as the majority of the FIFO buffer consists of the same data it did during the previous time step.
Instead, the PSD is analyzed once half of the buffer contains new data, e.g., if the time series length is 20 s, there will be 10 s between evaluations of the PSD.

Application states
------------------
The application utilize a state variable with the following states to track the status of the algorithm.

- :attr:`~acconeer.exptool.a121.algo.breathing._processor.AppState.NO_PRESENCE_DETECTED`: The algorithm did not detect any presence. If no presence is found, the algorithm initiates a new search.
- :attr:`~acconeer.exptool.a121.algo.breathing._processor.AppState.INTRA_PRESENCE_DETECTED`: Intra presence has been detected. Intra presence corresponds to a fast or large motion. If detected, the breathing analysis is paused. Once the intra presence is no longer detected, the distance to the person is again estimated as it might have changed due to the movement.
- :attr:`~acconeer.exptool.a121.algo.breathing._processor.AppState.DETERMINE_DISTANCE_ESTIMATE`: Determining the distance to the person using the presence processor.
- :attr:`~acconeer.exptool.a121.algo.breathing._processor.AppState.ESTIMATE_BREATHING_RATE`: Estimating the breathing rate in the segment where a person has been located.

The state is returned as a part of the reference application result, :attr:`~acconeer.exptool.a121.algo.breathing._ref_app.RefAppResult.app_state`

GUI
---
The following figure shows the Exploration Tool GUI of the breathing reference application.

The upper graph shows the inter and intra presence score.
The highlighted section of the traces indicates the region where the breathing rate is being analyzed.

The second graph shows the time series of the center point in the segment being analyzed.
The neighboring distances, also being analyzed, are not visualized to avoid cluttering the plot.

Next, the third plot shows the power spectrum of the time series.
The breathing rate is estimated as the peak location(plus interpolation as previously mentioned) of the PSD.

Lastly, the lower plot shows the history of the estimated breathing rate.
The solid blue line shows the estimated rate after each frame and the red dots show the output of the embedded implementation, outputting a new values when half of the buffer contains new data. Here, the person has an initial breathing rate of 12 bpm, transferring to a higher rate around 19 bpm.

.. image:: /_static/processing/a121_breathing_gui.png
    :width: 600
    :align: center

Calibration hints
-----------------
This section outlines a number of recommendations when calibrating the reference application.

- Use the presence processor to determine the distance to the person by setting :attr:`~acconeer.exptool.a121.algo.breathing._ref_app.RefAppConfig.use_presence_processor` to True.
- Set :attr:`~acconeer.exptool.a121.algo.breathing._ref_app.RefAppConfig.num_distances_to_analyze` so that the majority of the peak of the presence score is included in the breathing analysis.
- Use a duration between 5-10 s for the :attr:`~acconeer.exptool.a121.algo.breathing._ref_app.RefAppConfig.distance_determination_duration`.
- Adjust the intra presence threshold to minimize false triggers when breathing normally, but detecting anticipated movements. Anticipated movements refers to motions that does not originate from regular breathing, such as a person changing position.
- Select as high :attr:`~acconeer.exptool.a121.algo.breathing._ref_app.RefAppConfig.profile` as possible, while avoiding interference with the direct leakage. A larger starting point (:attr:`~acconeer.exptool.a121.algo.breathing._ref_app.RefAppConfig.start_m`) allows for a higher profile.
- Adjust :attr:`~acconeer.exptool.a121.algo.breathing._ref_app.RefAppConfig.sweeps_per_frame` to get good performance of the presence processor. The default value works well in general, but might have to be increased when measuring at longer distances.
- Once the sweeps per frame has been set, increase :attr:`~acconeer.exptool.a121.algo.breathing._ref_app.RefAppConfig.hwaas` to achieve better SNR.
- If needed, the :attr:`~acconeer.exptool.a121.algo.breathing._ref_app.RefAppConfig.frame_rate` can be lowered from the default of 20 Hz to reduce the memory and power consumption. A suitable value for an embedded application is 5-10Hz.

Use the predefined presets as a starting point and then tweak if necessary.

Practical considerations
------------------------
This section outlines a number of practical considerations when getting started with the breathing reference application.

- Start with one of the recommended presets, and then tune parameters if necessary.
- If there is a need to change the dynamics of the presence processor, do the tuning in the :doc:`presence algorithm</detectors/a121/presence_detection>` GUI as there is more visual feedback related to the presence algorithm. Once new parameter values has been determined, transfer them to the breathing reference application.
- When running the breathing reference application, aim the sensor towards the chest and stomach of the person for best performance.
- Use a lens when measuring at distances greater than 1 meter.

Tests
-----
This section presents results from testing the algorithm in various scenarios.

Test setup
^^^^^^^^^^
The tests were performed with an adult sitting, an adult lying down and an infant laying down.
The data collection and processing was done with the breathing reference application, available in Exploration tool.
The following pictures illustrates the setup.

.. image:: /_static/processing/a121_breathing_person.png
    :width: 600
    :align: center

Configuration
^^^^^^^^^^^^^
The presets, available in the Exploration tool, were used when testing.
In the case when the person is lying down at 2 meters(presented below), the end point of the sitting preset was extended to 2.5 m.

Results
^^^^^^^
The results from the testing are reported in the following table.

.. list-table:: Breathing reference application test results.
   :widths: 25 25 25 25
   :header-rows: 1

   * - Case
     - Distance to person (m)
     - Actual rate (bpm)
     - Estimate rate (bpm)
   * - Adult sitting
     - 1.0
     - 15.9
     - 15.0
   * - Adult lying down
     - 1.0
     - 18.3
     - 18.0
   * - Adult lying down
     - 2.0
     - 8.7
     - 9.0
   * - Infant lying down
     - 0.5
     - 18.4
     - 18.0


Configuration parameters
-------------------------
.. autoclass:: acconeer.exptool.a121.algo.breathing._ref_app.RefAppConfig
   :members:

.. autoclass:: acconeer.exptool.a121.algo.breathing._processor.BreathingProcessorConfig
   :members:

.. autoclass:: acconeer.exptool.a121.algo.breathing._processor.AppState
   :members:

Reference application result
----------------------------
.. autoclass:: acconeer.exptool.a121.algo.breathing._ref_app.RefAppResult
   :members:
