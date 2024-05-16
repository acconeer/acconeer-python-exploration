Detectors
=========

Detectors use the service data to produce a result that can be used by the application. User guides for the different Detectors are available at :ref:`a121_algorithms_detectors` and the Detectors are also available in the Exploration Tool.

Distance detector
----------------------

This is a distance detector algorithm built on top of the Sparse IQ service, where the filtered sweep is compared to a threshold to identify one or more peaks, corresponding to objects in front of the radar. More details about the detector are found at :doc:`/detectors/a121/distance_detection`.

Presence detector
-----------------

Detects changes in the environment over time based on data from the Sparse IQ service to determine human presence. More details about the detector are found at :doc:`/detectors/a121/presence_detection`.
