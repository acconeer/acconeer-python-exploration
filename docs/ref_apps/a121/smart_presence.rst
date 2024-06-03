Smart Presence
==============

Smart presence is based on the presence detector, see :ref:`exploration_tool-a121-presence_detection`.
The algorithm divides the presence detection range into multiple zones.
Furthermore, it has the possibility to change configuration based on detection, as well as configure how many zones that need to have detection before switching configuration.
This is perfect to utilize when a low power configuration is wanted for scanning and a more robust configuration is wanted to, e.g., track a person walking through the zones.
Smart presence has the same configuration possibilities as the presence detector, with the additions to create multiple zones in the range, utilize the wake up mode and to set how many zones that need to have detection before switching configuration.

Detection zones
---------------

The chosen range will be divided into the specified number of detection zones with equal size.
The maximum number of detection zones is the number of measured points in the chosen range.
To increase the maximum number of zones without extending the range, the step size can be decreased.
This will increase the number of sampling points at the cost of increased power consumption.
To get better distance resolution for the triggered zones, the chosen profile can be decreased. However, it should be remembered that the chosen profile needs to be large enough to get sufficient SNR in the complete range.
Furthermore, the pulse extends outside the chosen detection range, hence it is possible to detect presence slightly outside of the chosen range.
The extended detection range is dependent on the profile and is bounded by twice the full width at half maximum envelope power, see :ref:`rdac-a121-fom-radial-resolution`.

Detection types
---------------
As for the presence detector, both fast and slow motions are considered.
The triggered zones are reported back as a separate vector for fast motion detection, :attr:`~acconeer.exptool.a121.algo.smart_presence._ref_app.RefAppResult.intra_zone_detections`
and for slow motion detection, :attr:`~acconeer.exptool.a121.algo.smart_presence._ref_app.RefAppResult.inter_zone_detections`,
as well as one vector for the combined detections, :attr:`~acconeer.exptool.a121.algo.smart_presence._ref_app.RefAppResult.total_zone_detections`.
For both slow and fast motions, the zone with the highest presence score is returned.
The default for smart presence is to use both fast and slow motion detection to get a responsive detection, while at the same time having a stable detection when someone is being still.
Since the fast presence detection has lower time constants in the filtering it is more responsive than the slow motion detection, thus the triggered zones for fast and slow motions can differ.
The :attr:`~acconeer.exptool.a121.algo.smart_presence._ref_app.RefAppResult.max_presence_zone` is the zone with the most presence.
However, the fast presence is prioritized due to faster responsiveness, i.e., if fast presence is detected (regardless of if slow presence is detected or not), the zone with the highest fast presence score is returned.
If only slow presence is detected, the zone with the highest slow motion presence score is returned.

.. _wake_up_mode_section:

Wake up mode
------------
If :attr:`~acconeer.exptool.a121.algo.smart_presence._ref_app.RefAppConfig.wake_up_mode` is enabled, the application will change configuration based on whether presence is detected or not.
The wake up configuration has the possibility to divide the range into multiple zones, as well as setting how many zones that need detection in a two second period before switching configuration.
The two seconds period is created by having the zone linger its trigger for two seconds when the detection is lost.
When presence is detected, switching is automatically done to the nominal configuration. After switching, it takes some time before the nominal detector has gained detection due to the filtering in the presence detector.
Because of this, there is a latency when switching. During this time, presence is assumed detected. The maximum latency time is set based on the filter constants in the nominal presence configuration.
All the settings in the nominal configuration can be set differently compared to the wake up configuration if that is needed.
However, the nominal configuration does not have the parameter for setting the number of zones needed for switching, since this is not relevant.
The application will switch back to the wake up configuration when the presence detection is lost.

GUI
---
In the GUI, the fast and slow presence score together with their respective threshold is displayed for easy adjustments.
The detection zones are displayed in a circle sector.
When wake up mode is enabled, two circle sectors are displayed, one representing the wake up configuration and one representing the nominal configuration.
Green background indicates which configuration that is currently active.
The zones will be colored with different colors showing detection and detection type.
Blue indicates slow motion detection, orange indicates fast motion detection and green indicates that both have detection.
Light gray is an additional color for the wake up configuration. It represents the two seconds lingering detection of a zone that has lost its detection, see section :ref:`wake_up_mode_section` for more information.
In the circle sector for the nominal configuration, it is possible to have only the distance with the maximum presence score displayed or to display all detected zones.

The upper plots in the example in :numref:`smart_presence_gui` show that fast motions are not detected, and slow motions are detected.
The lower plot displays the range which is set to 1-3 m and that slow motions are detected in the middle zone.

.. _smart_presence_gui:
.. figure:: /_static/processing/a121_smart_presence_gui.png
    :align: center

    Example of the smart presence GUI. Inter presence is detecting presence in the middle zone, while intra presence is not detecting movement.

Tests
-----
Test cases
^^^^^^^^^^
**1. Human walking from Zone 3 -> Zone 1 (1-3 meters range)**

**2. Human walking through all zones from the side (1-3 meters range)**

**3. Human walking from Zone 3 -> Zone 1 (1-5 meters range)**

**4. Human walking through all zones from the side (1-5 meters range)**

**5. Human walking into wake up config and confirm detection. Continue walking and confirm detection is done with nominal config.**

**6. Human walking into wake up config and stops. Confirm detection in both wake up config and nominal config.**

**7. Ceiling mounted sensor. Human walking into wake up config and confirm detection. Continue walking and confirm detection is done with nominal config.**

**8. Ceiling mounted sensor. Human walking into wake up config and stops. Confirm detection in both wake up config and nominal config.**

Test setup
^^^^^^^^^^
In these tests the A121 EVK was used. In the first test cases, the EVK was mounted on a wall at the same height as the test person's torso, see :numref:`wall_setup`.

.. _wall_setup:
.. figure:: /_static/processing/smart_presence_setup.png
    :align: center

    Sensor mounted on the wall. Setup used for test cases 1-6.

In the later test cases, the EVK was mounted on the ceiling, see :numref:`ceiling_setup`.

.. _ceiling_setup:
.. figure:: /_static/processing/a121_smart_presence_ceiling.png
    :align: center

    Sensor mounted on the ceiling about 3 m up from the floor. Setup used for test cases 7 and 8.

Configuration
^^^^^^^^^^^^^
For test cases 1-4, the configuration in :numref:`table_smart_presence_configuration` was used.

.. _table_smart_presence_configuration:
.. list-table:: Smart presence configurations. Where applicable, if only one value is displayed, the same value was used for both wake up and nominal configuration.
   :header-rows: 1

   * - Parameter
     - Test cases 1-4
     - Short range wake up / nominal
     - Medium range wake up / nominal
     - Long range wake up / nominal
     - Ceiling wake up / nominal
   * - Range start
     - 1 m
     - 0.5 m / 0.06 m
     - 1.5 m / 0.3 m
     - 3 m / 2 m
     - 2 m / 1.5 m
   * - Range end
     - 3 m / 5 m
     - 1 m
     - 2.5 m
     - 5 m
     - 3.5 m
   * - Frame rate
     - 10 Hz
     - 2 Hz / 10 Hz
     - 2 Hz / 12 Hz
     - 2 Hz / 12 Hz
     - 4 Hz / 12 Hz
   * - Sweeps per frame
     - 32
     - 16
     - 16
     - 32
     - 24 / 18
   * - HWAAS
     - 16
     - 16
     - 32
     - 48
     - 32 / 18
   * - Inter frame idle state
     - Deep sleep
     - Deep sleep
     - Deep sleep
     - Deep sleep
     - Deep sleep
   * - Enable intra frame detection
     - True
     - True
     - True
     - True
     - True
   * - Intra detection threshold
     - 1.30
     - 1.50 / 1.40
     - 1.50 / 1.30
     - 1.40 / 1.20
     - 1.50 / 1.20
   * - Intra time constant
     - 0.15 s
     - 0.15 s
     - 0.15 s
     - 0.15 s
     - 0.15
   * - Intra output time constant
     - 0.50 s
     - 0.30 s
     - 0.30 s
     - 0.30 s
     - 0.25 s / 0.3 s
   * - Enable inter frame detection
     - True
     - True
     - True
     - True
     - True
   * - Enable phase boost
     - False
     - False
     - False
     - False
     - False / True
   * - Inter detection threshold
     - 1.0
     - 1.0
     - 1.0
     - 1.0 / 0.8
     - 1.0 / 0.8
   * - Inter fast cutoff frequency
     - 20.0 Hz
     - 5 Hz
     - 6 Hz
     - 6 Hz
     - 6 Hz
   * - Inter slow cutoff frequency
     - 0.2 Hz
     - 0.2 Hz
     - 0.2 Hz
     - 0.2 Hz
     - 0.2 Hz
   * - Inter time constant
     - 0.5 s
     - 0.5 s
     - 0.5 s
     - 0.5 s
     - 0.5 s
   * - Inter output time constant
     - 3.0 s
     - 2.0 s
     - 2.0 s
     - 2.0 s
     - 0.5 s / 2.0 s
   * - Inter presence timeout
     - 3 s
     - 3 s
     - 3 s
     - 3 s
     - 3 s
   * - Number of zones
     - 3
     - 1 / 5
     - 1 / 7
     - 5
     - 1
   * - Number of zones for wake up
     - -
     - 1
     - 1
     - 2
     - 1

Test cases 5 and 6 were tested for the short range, medium range and long range presets.
Test cases 7 and 8 were tested for the ceiling preset.

Results
^^^^^^^
**1. Human walking from Zone 3 -> Zone 1 (1-3 meters range)**

.. image:: /_static/processing/smart_presence_test1_a.png
    :width: 600
    :align: center

.. image:: /_static/processing/smart_presence_test1_b.png
    :width: 600
    :align: center


.. list-table:: Smart presence test results for test cases 1-4. All zones were detected successfully when walking towards the sensor and each zone was successfully detected when passing by.
   :widths: 25 25 25
   :header-rows: 1

   * - Zone
     - Walk towards
     - Pass by
   * - 0 (1-3 m range)
     - OK
     - OK
   * - 1 (1-3 m range)
     - OK
     - OK
   * - 2 (1-3 m range)
     - OK
     - OK
   * - 0 (1-5 m range)
     - OK
     - OK
   * - 1 (1-5 m range)
     - OK
     - OK
   * - 2 (1-5 m range)
     - OK
     - OK

**5. Human walking into wake up config and confirm detection. Continue walking and confirm detection is done with nominal config.**

.. figure:: /_static/processing/a121_smart_presence_short_nominal_config.png
    :width: 600
    :align: center

    Person detected in the middle detection zone with nominal configuration.

.. list-table:: Smart presence test results for test cases 5-8. Presence was detected and configuration changed successfully for all test cases.
   :widths: 25 25 25
   :header-rows: 1

   * - Preset
     - Walk
     - Walk and stop
   * - Short range
     - OK
     - OK
   * - Medium range
     - OK
     - OK
   * - Long range
     - OK
     - OK
   * - Ceiling
     - OK
     - OK

Configuration parameters
------------------------

.. autoclass:: acconeer.exptool.a121.algo.smart_presence._ref_app.RefAppConfig
    :members:
    :inherited-members:
    :undoc-members:
    :exclude-members: validate, from_dict, from_json, to_dict, to_json

.. autoclass:: acconeer.exptool.a121.algo.smart_presence._ref_app.PresenceZoneConfig
    :members:
    :inherited-members:
    :undoc-members:
    :exclude-members: validate, from_dict, from_json, to_dict, to_json

.. autoclass:: acconeer.exptool.a121.algo.smart_presence._ref_app.PresenceWakeUpConfig
    :members:
    :inherited-members:
    :undoc-members:
    :exclude-members: validate, from_dict, from_json, to_dict, to_json

Reference app result
--------------------
.. autoclass:: acconeer.exptool.a121.algo.smart_presence._ref_app.RefAppResult
   :members:
