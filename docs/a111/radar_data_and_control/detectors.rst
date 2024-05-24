Detectors
=========

Detectors take Service data as input and produce a result as the output that can be used by the application. Currently we have four Detectors available that produce different types of results and that are based on different Services. User guides for the different Detectors are available at `acconeer.com  <https://developer.acconeer.com/>`__ and the Detectors are also available in the Exploration Tool.

In addition, we provide several Reference applications which use Services or Detectors to demonstrate how to develop applications based on our technology, you can find these in the various SDKs at Acconeer developer site.


Distance detector
----------------------

This is a distance detector algorithm built on top of the :ref:`envelope-service` service -- based on comparing the envelope sweep to a threshold and identifying one or more peaks in the envelope sweep, corresponding to objects in front of the radar. The algorithm both detects the presence of objects and estimates their distance to the radar. More details about the detector is found `here <https://docs.acconeer.com/en/latest/processing/distance_detector.html>`__.


Presence detector
-----------------

Detects changes in the environment over time based on data from the Sparse service. More details about the detector is found `here <https://docs.acconeer.com/en/latest/processing/presence_detection_sparse.html>`__.


Obstacle detector
-----------------

Assumes that the Acconeer sensor is placed on a moving object with a known velocity, such as a robotic vacuum cleaner or lawn mower. The detector creates a virtual antenna array and uses synthetic aperture radar (SAR) signal processing to localize objects. This detector is used in the Obstacle localization demo movie. More details about the detector is found `here <https://docs.acconeer.com/en/latest/processing/obstacle.html>`__.
