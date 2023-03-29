Smart presence
==============

Smart presence will divide the presence detection range into multiple zones.
The algorithm is based on the presence detector, see :ref:`exploration_tool-a121-presence_detection`, and has the same configuration possibilities, with the addition to create multiple zones in the detection range.

Detection zones
---------------

For any chosen range, the range will be divided into the chosen number of detection zones with equal size.
The maximum number of detection zones is the number of points in the chosen range.
To increase the maximum number of zones without extending the range, the step size can be decreased.
This will increase the number of sampling points and thereby increase the power consumption.
To get better distance resolution in the zone detections, the chosen profile can be decreased. However, it should be remembered that the chosen profile needs to be large enough to get sufficient SNR in the complete range.
Furthermore, the chosen range is the range with optimal energy. Hence, detection can be seen both before the start point and beyond the end point.
The amount of extended detection is dependent on the chosen profile and can be estimated to never exceed twice the full width at half maximum envelope power, see :ref:`handbook-a121-fom-radial-resolution`.

Detection types
---------------
As for the presence detector, both fast and slow motions are considered. The zone detections can either be used separately for the two detection types or all detected zones, independent of detection type, can be used.
For both slow and fast motions, the zone with the highest presence score is returned together with the detection result for all zones.
The default for smart presence is to use both fast and slow motion detection to get fast detection, while at the same time having a stable detection when someone is standing still.
Since the fast presence detection has lower time constants in the filtering it is more responsive than the slow motion detection, thus the zone detections for fast and slow motions can differ.
The :attr:`~acconeer.exptool.a121.algo.smart_presence._ref_app.RefAppResult.max_presence_zone` is the zone with the most presence.
However, the fast presence is prioritized due to faster responsiveness, i.e., if fast presence is detected (regardless of if slow presence is detected or not), the zone with highest fast presence score is returned.
If only slow presence is detected, the zone with highest slow motion presence score is returned.

GUI
---
In the GUI, the fast and slow presence score together with their respective threshold is displayed for easy adjustments.
The detection zones are displayed in a circle sector with different colors showing detection and detection type.
In the circle sector, it is possible to have only the distance with the maximum presence score displayed or to show all detected zones.
The example upper plots show that fast motions are not detected, and slow motions are detected.
The lower plot displays the range which is set to 1-3 m and that slow motions are detected in the second zone.

.. image:: /_static/processing/a121_smart_presence_gui.png
    :align: center

Tests
-----
Test setup
^^^^^^^^^^
In these tests the A121 EVK was used. The EVK was mounted on a wall at the same height as the test person's torso.

.. image:: /_static/processing/smart_presence_setup.png
    :align: center

Test cases
^^^^^^^^^^
**1. Human walking from Zone 3 -> Zone 1 (1-3 meters range)**

**2. Human walking through all zones from the side (1-3 meters range)**

**3. Human walking from Zone 3 -> Zone 1 (1-5 meters range)**

**4. Human walking through all zones from the side (1-5 meters range)**

Configuration
^^^^^^^^^^^^^
.. list-table:: Smart presence configuration
   :widths: 25 25
   :header-rows: 0

   * - Range start
     - 1 m
   * - Range end
     - 3 m / 5 m
   * - Frame rate
     - 10 Hz
   * - Sweeps per frame
     - 32
   * - HWAAS
     - 16
   * - Inter frame idle state
     - Deep sleep
   * - Enable intra frame detection
     - True
   * - Intra detection threshold
     - 1.30
   * - Intra time constant
     - 0.15 s
   * - Intra output time constant
     - 0.50 s
   * - Enable inter frame detection
     - True
   * - Enable phase boost
     - False
   * - Inter detection threshold
     - 1.0
   * - Inter fast cutoff frequency
     - 20.0 Hz
   * - Inter slow cutoff frequency
     - 0.2 Hz
   * - Inter time constant
     - 0.5 s
   * - Inter output time constant
     - 3.0 s
   * - Inter presence timeout
     - 3 s
   * - Number of zones
     - 3

Results
^^^^^^^
**1. Human walking from Zone 3 -> Zone 1 (1-3 meters range)**

.. image:: /_static/processing/smart_presence_test1_a.png
    :width: 600
    :align: center

.. image:: /_static/processing/smart_presence_test1_b.png
    :width: 600
    :align: center


.. list-table:: Smart presence test results. All zones were detected successfully when walking towards the sensor and each zone was successfully detected when passing by.
   :widths: 25 25 25
   :header-rows: 1

   * - Zone
     - Walk towards
     - Pass by
   * - 0 (1-3 m range)
     - X
     - X
   * - 1 (1-3 m range)
     - X
     - X
   * - 2 (1-3 m range)
     - X
     - X
   * - 0 (1-5 m range)
     - X
     - X
   * - 1 (1-5 m range)
     - X
     - X
   * - 2 (1-5 m range)
     - X
     - X

Configuration parameters
------------------------

.. autoclass:: acconeer.exptool.a121.algo.smart_presence._ref_app.RefAppConfig
    :members:
    :inherited-members:
    :undoc-members:
    :exclude-members: validate, from_dict, from_json, to_dict, to_json

Reference app result
--------------------
.. autoclass:: acconeer.exptool.a121.algo.smart_presence._ref_app.RefAppResult
   :members:
