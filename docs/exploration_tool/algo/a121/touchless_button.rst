Touchless button
=====================

This reference application aims to show how the A121 sensor can be implemented as a touchless button.

The application works for two different ranges, one close to the sensor and one further away.
The intended close range is from the sensor to 0.05 m and the intended far range is from the sensor to approximately 0.24 m, but may register events slightly outside the range.
The application works for further ranges as well if the sensor settings are adjusted.

The processor has three different measurement types; one for close range, one for far range and one for both.
If both ranges are used the processor output will consist of two booleans, each indicating the button state for one range.

Each range consists of one subsweep and can therefore be modified separately.
The close range subsweep utilizes a shorter profile (:attr:`~acconeer.exptool.a121.Profile.PROFILE_1`) to be able to detect smaller objects such as fingers while the far range subsweep utilizes a longer profile (:attr:`~acconeer.exptool.a121.Profile.PROFILE_3`) and reacts on larger objects such as hands.

Calibration
-----------
Each subsweep consists of a multiple number of points (:attr:`~acconeer.exptool.a121.SubsweepConfig.num_points`), where each point corresponds to a distance.
All points are calibrated separately and continuously.
The threshold for each point is calculated from the number of frames received during the time set by :attr:`~acconeer.exptool.a121.touchless_button.processor.calibration_duration_s` together with the sensitivity for each range (:attr:`~acconeer.exptool.a121.touchless_button.processor.sensitivity_close` and :attr:`~acconeer.exptool.a121.touchless_button.processor.sensitivity_far`).
The threshold will continuously be updated as long as there are no detections at any range.
Thus, the processor might show slightly different behavior when running both ranges at the same time versus running them separately on the same data.

Data processing
---------------
The processor will for each frame determine if the sweeps are significantly above the threshold or not.
It will register a significant frame on the chosen range/ranges, when at least two sweeps at the same depth are above the threshold in the same frame.
The patience-setting (:attr:`~acconeer.exptool.a121.touchless_button.processor.patience_close` and :attr:`~acconeer.exptool.a121.touchless_button.processor.patience_far`) determines how many frames in a row must be significant in the chosen range to count as a detection.
It also determines how many frames in a row must be nonsignificant to count as the end of the detection.
Increasing the patience setting will make the button detect only slower movements and longer presence in front of the sensor, thus making the button less responsive.
Increasing the number of sweeps per frame will make the detection slower but increase the probability of a detection within the frame.

Since the data from the A121 sensor is complex, each data point includes both phase and amplitude information.
The threshold takes advantage of both the real and imaginary part of the data and can be seen as an ellipsis-shaped boundary is the complex plane.
A data point can pass the threshold by either a shift in phase (which would be caused by movement), a shift in amplitude (which would be caused by a more reflecting object) or both at the same time. Which in turn will trigger a detection.

Configuration parameters
------------------------
.. autoclass:: acconeer.exptool.a121.algo.touchless_button.ProcessorConfig
   :members:
