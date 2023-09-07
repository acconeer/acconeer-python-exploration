Touchless button
=====================

The purpose of the touchless button reference application is to employ the A121 sensor as a contactless button. This algorithm proves useful in scenarios where registering a button press is needed without physically touching a surface. A prime example would be in public spaces. Moreover, the algorithm is designed to automatically recalibrate itself when static objects obstruct the sensor, preventing prolonged and erroneous detections.

Measurement Range and Presets
------------------------------
The reference application is designed to have two different detection ranges: one in close proximity to the sensor and another farther away. Users can choose which range, or even both, to activate simultaneously.

The close range is defined as the zone from the sensor up to 5 centimeters, while the far range spans from the sensor to roughly 24 cenitmeters. These ranges are presented in three preset configurations within the Exploration Tool: one for exclusive close range detection, another for exclusive far range detection, and a third for detecting in both ranges.

It's important to note that the algorithm can also accommodate extended ranges, provided the sensor settings are appropriately adjusted to encompass a larger distance.

Configuration
--------------
Each detection range is composed of a single subsweep, allowing for independent configuration and adjustment of each range.

The :attr:`~acconeer.exptool.a121.algo.touchless_button.ProcessorConfig.measurement_type` processing parameter is used to activate a specific range and set which patience and sensitivity processing parameters to apply during the processing.

The sensitivity parameters (:attr:`~acconeer.exptool.a121.algo.touchless_button.ProcessorConfig.sensitivity_close`  and :attr:`~acconeer.exptool.a121.algo.touchless_button.ProcessorConfig.sensitivity_far`) establish the detection threshold for each range. Meanwhile, the patience parameters (:attr:`~acconeer.exptool.a121.algo.touchless_button.ProcessorConfig.patience_close` and :attr:`~acconeer.exptool.a121.algo.touchless_button.ProcessorConfig.patience_far`) dictate the consecutive frame count above the threshold required to recognize a button press, as well as the consecutive frames below the threshold to signify the end of a button press action.

Calibration
------------

Each subsweep is comprised of multiple points (``num_points``), with each point corresponding to a distance in space where reflected pulses are measured. These points undergo continuous individual calibration. The threshold is normalized for each point by evaluating the standard deviation in the number of sweeps received during the :attr:`~acconeer.exptool.a121.algo.touchless_button.ProcessorConfig.calibration_duration_s` period. This threshold normalization remains dynamically updated as long as no detections occur within any range. Consequently, there might be slight variations in the processor result when both ranges are simultaneously active compared to their separate activation on the same data.

To change the calibration to include more or fewer frames, the configuration parameter :attr:`~acconeer.exptool.a121.algo.touchless_button.ProcessorConfig.calibration_duration_s` should be increased or decreased respectively. Note that during the calibration no button press actions should be performed since the purpose of the calibration is to record the background noise.

The :attr:`~acconeer.exptool.a121.algo.touchless_button.ProcessorConfig.calibration_interval_s` configuration parameter establishes the maximum time interval in seconds between successive calibrations. When a consecutive detection reaches the time limit set by :attr:`~acconeer.exptool.a121.algo.touchless_button.ProcessorConfig.calibration_interval_s`, a fresh calibration is initiated. The purpose of the parameter is to adjust the normalization of the detection threshold to effectively respond to significant environmental changes, such as the introduction of static objects within the detection range. Therefore, :attr:`~acconeer.exptool.a121.algo.touchless_button.ProcessorConfig.calibration_interval_s` should not be set lower than the estimated duration of the longest continuous detection event.

Processing
------------

For every frame, the processor evaluates whether the sweeps significantly surpass the threshold or not. In the selected range or ranges, a frame is recorded as significant when a minimum of two sweeps at the same distance surpass the threshold within the same frame. The patience settings (:attr:`~acconeer.exptool.a121.algo.touchless_button.ProcessorConfig.patience_close` and :attr:`~acconeer.exptool.a121.algo.touchless_button.ProcessorConfig.patience_far`) dictate the number of consecutive significant frames needed for the event to be deemed as a valid detection (button press). Similarly, it specifies the number of consecutive frames required to be nonsignificant to signal the end of a detection event. Increasing the patience setting results in the button detecting prolonged presence in front of the sensor, consequently reducing its responsiveness. However, it decreases the risk of false detections if short sporadic noise appears.

Since the data from the A121 sensor is complex, each data point includes both phase and amplitude information. The threshold takes advantage of both the real and imaginary part of the data and can be seen as an circular boundary in the complex plane. A data point can pass the threshold by either a shift in phase (which would be caused by movement), a shift in amplitude (which would be caused by a more reflecting object) or both at the same time. Which in turn will trigger a detection. The placement of the circular boundary in the complex plane is determined by the mean and standard deviation of the calibration frames measured during the time set by :attr:`~acconeer.exptool.a121.algo.touchless_button.ProcessorConfig.calibration_duration_s` and the radius of the boundary is set by the sensitivity parameters (:attr:`~acconeer.exptool.a121.algo.touchless_button.ProcessorConfig.sensitivity_close` and :attr:`~acconeer.exptool.a121.algo.touchless_button.ProcessorConfig.sensitivity_far`). Opting for a high sensitivity setting results in a smaller radius, leading to a lower threshold. Conversely, a low sensitivity setting produces a larger radius, subsequently yielding a higher threshold.

Results
---------

The algorithm will provide six different results, three for each range: detection, threshold and detection score.

The result parameters :attr:`~acconeer.exptool.a121.algo.touchless_button.ProcessorResult.detection_close` and :attr:`~acconeer.exptool.a121.algo.touchless_button.ProcessorResult.detection_far` will simply declare if there is detection within the range. The parameters will be ``True`` for detection, ``False`` for no detection and ``None`` if the range is not activated.

The detection scores parameters will provide the detection score for each point in each subsweep. The output shape will therefore be (:attr:`~acconeer.exptool.a121.SessionConfig.SensorConfig.sweeps_per_frame`, number of points in current subsweep). The detection score will be ``None`` if the range is not activated.

The parameters :attr:`~acconeer.exptool.a121.algo.touchless_button.ProcessorResult.threshold_close` and :attr:`~acconeer.exptool.a121.algo.touchless_button.ProcessorResult.threshold_far` gives the threshold to which the detection scores are compared against. The thresholds are inversely proportional to the sensitivity parameters where :attr:`~acconeer.exptool.a121.algo.touchless_button.ProcessorResult.threshold_close` ``= 10 /`` :attr:`~acconeer.exptool.a121.algo.touchless_button.ProcessorConfig.sensitivity_close` and :attr:`~acconeer.exptool.a121.algo.touchless_button.ProcessorResult.threshold_far` ``= 10 /`` :attr:`~acconeer.exptool.a121.algo.touchless_button.ProcessorConfig.sensitivity_far`.

GUI
-----

In the GUI two plots are displayed, see :numref:`touchless_button_gui`. The top plot shows the detection duration for the close and far range. The displayed range can be changed by switching the *Range* parameter under *Processor parameters* in the GUI or switch preset under *Preset Configurations*.

The bottom plot displays the detection score for each distance point in each range. To hide thresholds or points click on the corresponding symbol in the legend. The points represent the 2nd highest detection score per frame for each distance. The 2nd highest score is chosen for plotting since a frame counts as significant after two points at the same distance pass the threshold during the same frame. A detection in the activated range(s) will be shown in the top plot when the consecutive number of points above the threshold is greater or equal to the patience parameter for the activated range(s). The purpose of the bottom plot is to demonstrate the effect of the sensitivity settings and to give the user an idea of which points are most important for the user’s detection scenario. The sensitivity settings might need to be adjusted depending on integration and purpose of the application. The sensitivity will always result in a trade-off between missed detections and false detections.

.. _touchless_button_gui:
.. figure:: /_static/processing/a121_touchless_button_gui.png
    :align: center

    Example of the touchless button GUI. Detection is found in both the close and far range. The threshold for each range and the detection score for each distance is shown in the lower plot.

Tests
--------
The following section presents the results from various tests on the algorithm.

Presets range test
^^^^^^^^^^^^^^^^^^^
The purpose of this test was to check that no detections are made outside the appointed range for each preset. Close range should not have detections outside 0.05 m and far range should not have detections outside 0.24 m.

**Test setup**

For this test an A121 EVK (XC120 + XE121) was used. To test the presets a corner reflector was moved just outside the edge of the appointed ranges (0.05 m and 0.24 m), see :numref:`touchless_button_presets_test`.

.. _touchless_button_presets_test:
.. figure:: /_static/processing/touchless_button_presets_range_test.jpg
    :align: center

    Test setup to test preset ranges, to ensure no detection outside the range.

**Configurations**

The configurations below corresponds to the presets in Exploration Tool, see :numref:`table_touchless_button_presets_test_configuration`.

.. _table_touchless_button_presets_test_configuration:
.. list-table:: Touchless button configurations.
   :header-rows: 1

   * - Parameter
     - Close range
     - Far range
   * - Sensitivity
     - 1.9
     - 2.0
   * - Patience
     - 2
     - 2
   * - Calibration duration
     - 0.6 s
     - 0.6 s
   * - Calibration interval
     - 20.0 s
     - 20.0 s
   * - Sweeps per frame
     - 16
     - 16
   * - Sweep rate
     - 320 Hz
     - 320 Hz
   * - Inter sweep idle state
     - Ready
     - Ready
   * - Inter frame idle state
     - Ready
     - Ready
   * - Continous sweep mode
     - True
     - True
   * - Double buffering
     - True
     - True
   * - Start point
     - 0
     - 0
   * - Number of points
     - 3
     - 3
   * - Step length
     - 6
     - 24
   * - HWAAS
     - 40
     - 60
   * - Profile
     - 1
     - 3

**Results**

No detection outside any of the ranges.

Persons test
^^^^^^^^^^^^
The algorithm was tested on 10 different people to evaluate the functionality of the algorithm.

**Test setup**

For this test an A121 EVK (XC120 + XE121) was used integrated with a blinkstick to give the user direct response on their action. The setup was encapsulated in a 3D-printed cover. No lens was used. See :numref:`touchless_button_persons_test`.

10 different people were asked to perform a tap with the back of their hand/fingers towards the sensor, as if they were tapping a button to open a door on for example a buss or a train. The action counted as detected if either or both of the ranges (close range and far range) detected the action.

.. _touchless_button_persons_test:
.. figure:: /_static/processing/a121_touchless_button_persons_test.png
    :align: center

    Shows the setup and action used in the persons test.

**Configurations**

This test utilized the "Close and far range" preset in Exploration Tool. This preset uses two subsweeps, the subsweep configurations can be seen in :numref:`table_touchless_button_presets_test_configuration`.

**Results**

.. list-table:: Results from persons test.
   :header-rows: 1

   * -
     - Number of detections
     - Number of actions
   * - Person 1
     - 10
     - 10
   * - Person 2
     - 10
     - 10
   * - Person 3
     - 10
     - 10
   * - Person 4
     - 10
     - 10
   * - Person 5
     - 10
     - 10
   * - Person 6
     - 10
     - 10
   * - Person 7
     - 10
     - 10
   * - Person 8
     - 10
     - 10
   * - Person 9
     - 10
     - 10
   * - Person 10
     - 10
     - 10

Comments regarding changes in temperature
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Changing temperature will affect the SNR of the signal. At lower temperatures the SNR is increased and at higher temperatures the SNR is decreased. Some actions will therefore trigger detection easier at lower temperatures and the sensitivity can threrefore be set lower at these termperatures. It is therefore favorable to set the sensitivity according to the desired responsiveness at the highest estimated temperature for the intended integration. The sensitivities selected for the presets were chosen to minimize missed detections and false detections in the range -10°C and 50°C. The evaluation was made using 8 different sensors at three different temperatures: -10°C, 25°C and 50°C.

Processor Configuration
--------------------------
.. autoclass:: acconeer.exptool.a121.algo.touchless_button.ProcessorConfig
   :members:

Result
------------------
.. autoclass:: acconeer.exptool.a121.algo.touchless_button.ProcessorResult
   :members:

.. autoclass:: acconeer.exptool.a121.algo.touchless_button.RangeResult
   :members:
