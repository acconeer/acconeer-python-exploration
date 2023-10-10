Obstacle Bilateration
=====================

This example runs the :doc:`Obstacle detector</exploration_tool/algo/a121/detectors/obstacle_detection>` with two sensors and bilateration enabled.

Motivation
----------
One limitation with the single sensor Obstacle detector is that the magnitude of the angle relative to the direction of motion is calculated. If an object is seen at 30 degrees, it is not known if it is to the left or right, or up or down. Therefore, in use-cases where the radar is mounted on a robot, it is difficult to separate the scenarios that the robot is moving below a table or next to wall, since both will be seen as strongly reflecting object 90 degrees from the direction of motion.

By utilizing the improved distance accuracy in A121 radar sensor, two sensors can be placed only a few centimeters apart on the robot, and the distance difference to an object can be used to estimate the angle to the object. This bilateration angle, together with the standard obstacle angle, can place the object correctly up/left/right.


Detector Configuration
----------------------
.. autoclass:: acconeer.exptool.a121.algo.obstacle.DetectorConfig
   :members:

Bilateration Result
-------------------
.. autoclass:: acconeer.exptool.a121.algo.obstacle._bilaterator.BilateratorResult
   :members:
