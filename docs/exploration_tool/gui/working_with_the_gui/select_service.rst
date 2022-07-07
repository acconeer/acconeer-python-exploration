.. _gui-select-service:

Choosing a service or detector
==============================

At this point, you should have connected to your sensor via one of the available options.
By default, the GUI selects the Envelope service, if no other service has been selected.
Other services or detectors can be selected via the drop down list.

Our sensor can be run in one of these four basic services:

+---------------------------+------------------------------+-----------------------------------------------------------------------+
| **Service**               | **Data Type**                | **Example Use Case**                                                  |
+===========================+==============================+=======================================================================+
| :ref:`envelope-service`   | | Amplitude only             | | Absolute distance (e.g. water level)                                |
| (:ref:`pb-service`)       |                              | | Static presence (e.g. parking sensor)                               |
+---------------------------+------------------------------+-----------------------------------------------------------------------+
| :ref:`iq-service`         | | Amplitude and Phase        | | Obstacle detection (e.g. lawn mower, RVC, <30 cm/s)                 |
|                           |                              | | Breathing                                                           |
|                           |                              | | Relative distance (down to 50 microns)                              |
+---------------------------+------------------------------+-----------------------------------------------------------------------+
| :ref:`sparse-service`     | | Instantaneous amplitude    | | Speed (up to m/s)                                                   |
|                           | | at high rep-rate           | | Presence detection (moving objects)                                 |
|                           |                              | | People counting                                                     |
+---------------------------+------------------------------+-----------------------------------------------------------------------+

.. _select-service-figure:
.. figure:: /_static/gui/select_service.png
    :figwidth: 40%
    :align: right

    Service and detector drop-down menu in the GUI

Each of these services has it's own advantages and disadvantages and knowing about the capabilities of each service will help you select the correct one for your use-case.

In order to better understand the type of information you can get with each service, the GUI can be used to look at the unprocessed data of each of those.
Just select any of those services from the **Select service and detectors** drop-down menu and click **Start measurement**.

.. attention::
    Using the Acconeer Exploration Tool interface, you can only use one service/detector at a time. Even when using several sensors, you cannot use different service types or detectors on different sensors with the GUI.

Detectors
---------
Each detector is based on one of the above listed services, but applies post-processing to the data in order to work out the information relevant to the detector.
In the drop-down list, you can see the used service added in brackets after the detector name (see :numref:`select-service-figure`).
At the moment we have the following examples and detectors to choose from:

#. **Envelope Service**

   - :ref:`Distance Detection <distance-detector>`  (Detector)
   - :ref:`Button Press <button-press>` (Example)

#. **IQ Service**

   - :ref:`Phase Tracking <phase-tracking>` (Example)
   - Breathing (Example)
   - :ref:`Sleep Breathing <sleep-breathing>` (Example)
   - :ref:`Obstacle Detection <obstacle-detection>` (Detector)

#. **Sparse Service**

   - :ref:`Presence Detection <sparse-presence-detection>` (Detector)
   - Sparse short-time FFT (Example)
   - Sparse long-time FFT (Example)
   - Speed (Example)

The main difference between a detector and an example is that for detectors, we have the matching C-code available.

.. tip::
    All settings and names you can find for the detector in the GUI are kept the same in the C-code and the processing is identical to allow tuning parameters in the GUI and just copy & pasting the settings to your C-code implementation.
