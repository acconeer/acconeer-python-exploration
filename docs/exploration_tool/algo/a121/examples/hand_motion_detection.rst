Hand motion detection
=====================

The purpose of the hand motion detection algorithm is to detect the presence of a pair of hands in front of the faucet in a sink.
In the typical application, the goal is to minimize the water consumption by turning the faucet on and off, based on the output of the algorithm.

To achieve low power consumption, thereby enabling the usage of battery, the hand motion detection algorithm is paired with the
:doc:`presence detector</exploration_tool/algo/a121/detectors/presence_detection>`,
monitoring the presence of a human in the vicinity of the sink.
If presence is detected, the application switches over from the presence detector mode to the hand motion detection mode.
Once hand motion is no longer detected, the application switches back to the low power mode.

Algorithm outline
-----------------

The hand motion detection algorithm detects the presence of a pair of hands moving in front of the sensor by calculating the amount of variation of the data within a frame and over consecutive frames.
The result is compared to the noise floor of the system and finally compared to a user defined threshold.

A number of configuration parameters are available (see later section in this guide), controlling the responsiveness and robustness of the algorithm.

Algorithm modes
---------------

The algorithm can run in the following two modes:

- :attr:`~acconeer.exptool.a121.algo.hand_motion.AppMode.PRESENCE`: Presence detector, configured to run at low power consumption.
- :attr:`~acconeer.exptool.a121.algo.hand_motion.AppMode.HANDMOTION`: Hand motion detection, designed to be responsive.

The current running mode is returned as part of the application result through the variable
:attr:`~acconeer.exptool.a121.algo.hand_motion.ModeHandlerResult.app_mode`.

The algorithm can be configured to only run in the hand motion detection mode if power consumption is not a requirement.

Configuration
-------------

The configuration is divided into three subsets of configuration parameters.

**Example application configuration**

The example application configuration handles the switching between the presence mode (low power)
and the hand motion detection mode.

- :attr:`~acconeer.exptool.a121.algo.hand_motion.ModeHandlerConfig.use_presence_detection` : Controls whether or not to use the presence detector based low power mode. In a battery driven application, the usage of this mode will increase the battery life time. If the system is driven by power from the grid, and power consumption is not an issue, this mode can be disabled.
- :attr:`~acconeer.exptool.a121.algo.hand_motion.ModeHandlerConfig.hand_detection_timeout` : Controls the duration in the hand motion detection mode without detection before returning to the low power mode.

**Presence detection configuration**

For details on the presence detector configuration and how to configure, follow
:doc:`this link</exploration_tool/algo/a121/detectors/presence_detection>`.

**Hand motion detection configuration**

The configuration has three parameters, related to the physical installation of the sensor and
geometry of the faucet.
The parameters are described below, followed by picture, illustrating their relationship.

- :attr:`~acconeer.exptool.a121.algo.hand_motion.ExampleAppConfig.sensor_to_water_distance`: The distance from the sensor to the center of the water jet (m).
- :attr:`~acconeer.exptool.a121.algo.hand_motion.ExampleAppConfig.water_jet_width`: The water jet width. Note, when setting this parameters, it is good to consider the maximum variation of the water jet over the life time of the system, including clogging and other sources of water jet width variation (m).
- :attr:`~acconeer.exptool.a121.algo.hand_motion.ExampleAppConfig.measurement_range_end` : End point of the measurement range (m). The end of the measurement range is the location where the detection of the hand should start, for instance the end of the sink.

.. image:: /_static/processing/a121_faucet_setup.png
    :align: center
    :width: 45%

The range related sensor configuration parameters are automatically determined based on these three configuration parameters, including the usage of subsweeps, utilized to capture data in front of and behind the water jet, while avoiding effects from the motion of the water jet.

Next, the following three parameters are related to the responsiveness and robustness of the detection:

- :attr:`~acconeer.exptool.a121.algo.hand_motion.ExampleAppConfig.filter_time_const`: Filter time constant of the algorithm. A higher value yield a more robust but less responsive performance.
- :attr:`~acconeer.exptool.a121.algo.hand_motion.ExampleAppConfig.threshold`: The threshold against which the detection metric is compared to.
- :attr:`~acconeer.exptool.a121.algo.hand_motion.ExampleAppConfig.detection_retention_duration`: Duration of retaining the detection after the metric is below the threshold. Setting the time to 0 s disables the retention.

Lastly,
:attr:`~acconeer.exptool.a121.algo.hand_motion.ExampleAppConfig.hwaas`,
:attr:`~acconeer.exptool.a121.algo.hand_motion.ExampleAppConfig.sweeps_per_frame`,
:attr:`~acconeer.exptool.a121.algo.hand_motion.ExampleAppConfig.sweeps_rate` and
:attr:`~acconeer.exptool.a121.algo.hand_motion.ExampleAppConfig.frame_rate`
are all sensor configuration parameters.
For more information regarding these parameters see :ref:`api_a121_configs`.

Configuration hints
-------------------

The following hints should be used as a starting point when setting up application, from which further manual tuning might be needed to optimize the performance.

- With the water turned off, adjust :attr:`~acconeer.exptool.a121.algo.hand_motion.ExampleAppConfig.filter_time_const`, :attr:`~acconeer.exptool.a121.algo.hand_motion.ExampleAppConfig.threshold` and :attr:`~acconeer.exptool.a121.algo.hand_motion.ExampleAppConfig.detection_retention_duration` to get desired response.
- Set the parameters :attr:`~acconeer.exptool.a121.algo.hand_motion.ExampleAppConfig.sensor_to_water_distance`, :attr:`~acconeer.exptool.a121.algo.hand_motion.ExampleAppConfig.water_jet_width` and :attr:`~acconeer.exptool.a121.algo.hand_motion.ExampleAppConfig.measurement_range_end` according to the sensor installation and faucet setup.
- Make sure that the algorithm does not detect running water by starting the water flow and observing the hand motion metric, visualized in Exploration Tool. If the water causes the metric to go over the threshold, increase :attr:`~acconeer.exptool.a121.algo.hand_motion.ExampleAppConfig.water_jet_width` to further increase size the region not being measured an/or increase the :attr:`~acconeer.exptool.a121.algo.hand_motion.ExampleAppConfig.threshold`.
- Tuning the parameters of the presence detector is easily done in the :doc:`presence detector</exploration_tool/algo/a121/detectors/presence_detection>` application, available in Exploration Tool. Once a satisfactory configuration is found, transfer the parameters back to this application.

Result
------

The result object contains the complete result from the underlying presence detector and
hand motion example application, in the two members
:attr:`~acconeer.exptool.a121.algo.hand_motion.ModeHandlerResult.presence_result` and
:attr:`~acconeer.exptool.a121.algo.hand_motion.ModeHandlerResult.hand_motion_result`.

But more importantly, it also contains the two following members

- :attr:`~acconeer.exptool.a121.algo.hand_motion.ModeHandlerResult.app_mode` indicating the current operation mode of the application

   - :attr:`~acconeer.exptool.a121.algo.hand_motion.AppMode.PRESENCE` - Detecting presence in the vicinity if the sink.
   - :attr:`~acconeer.exptool.a121.algo.hand_motion.AppMode.HANDMOTION` - Presence has been detected. Now scanning for hand motion in the vicinity of the faucet.

- :attr:`~acconeer.exptool.a121.algo.hand_motion.ModeHandlerResult.detection_state` indicating the state of detection when running in the hand detection mode.

   - :attr:`~acconeer.exptool.a121.algo.hand_motion.DetectionState.NO_DETECTION` - No hand detected.
   - :attr:`~acconeer.exptool.a121.algo.hand_motion.DetectionState.DETECTION` - Hand is currently being detected.
   - :attr:`~acconeer.exptool.a121.algo.hand_motion.DetectionState.RETENTION` - Hand has previously been detected. Retaining detection for :attr:`~acconeer.exptool.a121.algo.hand_motion.ExampleAppConfig.detection_retention_duration` seconds.

Configuration classes
---------------------

.. autoclass:: acconeer.exptool.a121.algo.hand_motion.ModeHandlerConfig
   :members:

.. autoclass:: acconeer.exptool.a121.algo.hand_motion.ExampleAppConfig
   :members:

Result class
------------

.. autoclass:: acconeer.exptool.a121.algo.hand_motion.ModeHandlerResult
   :members:

Application classes
-------------------

.. autoclass:: acconeer.exptool.a121.algo.hand_motion.AppMode
   :members:

.. autoclass:: acconeer.exptool.a121.algo.hand_motion.DetectionState
   :members:
