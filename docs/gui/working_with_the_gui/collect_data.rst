.. _collect-data:

Collect data
============
The Python Exploration Tool GUI makes it very easy to collect data, be it for evaluation, testing or in-depth detector tuning or development.
At the heart of the data collection are the functions for starting and stopping a scan and saving and loading the data that has been collected in this way.
As mentioned in the introduction to *Working with the GUI*, the GUI never stores processed data, only the un-processed service data received from the sensor.
Thus, you can always go back and refine processing on the original, unmodified service data.

At this point, we assume that you have

- :ref:`connected to a sensor <connect-sensor>`
- selected a :ref:`service or detector <gui-select-service>`
- and configured the sensor (:ref:`pb-service`, :ref:`envelope-service`, :ref:`iq-service`, :ref:`sparse-service`).

.. _start-stop:

Start and stop a scan
^^^^^^^^^^^^^^^^^^^^^
If this is the first time you are using our sensor, we recommend you to select the **Envelope** service and leave all sensor settings at their default values.
Place the sensor so that there is no object between 20 and 80 cm distance to it.
Keep in mind that the sensor has a very large field of view (FOV) of more than 40 degrees (with no lens attached).
Click **Start measurement** and observe the graph area to the left side of the GUI.
It should look similar to this:

.. figure:: /_static/gui/empty_scan.png

   Free space scan using Envelope

In the top left graph, you can see the envelope of the received radar signal.
It should be quite flat, but if you have a table with a rough surface or any object within the scanning range of the sensor, you will see an increase of amplitude at that distance.
Now, place an object (a cup or a glass) at a distance of ~30 to 60 cm in front of the sensor and observe the change in response.
It should look similar to the following figure:

.. figure:: /_static/gui/object_scan.png

   Scanning distance to an object using Envelope

Now you should be seeing a distinct peak in the amplitude plot, at the distance where you placed the object.
Move the object slightly in distance to see the peak moving forward and backward.
On the bottom plot, you can see the history of the amplitude measurements over the last few seconds (the exact length of the history can be set in the **Processing settings** tab under *History length*).

.. attention::
    You will likely see more than one peak and also a rather broad peak.
    The second peak is often coming from multiple reflections (in above picture, likely from within the semi-transparent glass).
    Since the whole glass front facing the sensor is reflecting radar, the peak gets broadened and represents an average response of the glass to the radar.
    Even with a point-like object, the response will have a certain spread due to the radar pulse having a certain duration in time.

You may try objects of different sizes, shapes and materials to see how and if the radar response changes.
When using flat objects, experiment with rotation of the flat surface; radar reflects off flat surfaces just like visible light in a mirror and at a certain rotation of the surface you will see the signal vanishing completely!

To see the impact of the pulse duration on peak spread, stop the scan by clicking **Stop** and change the **Profile** to a higher or lower number and start the scan again (for more details, see the :ref:`Sensor introduction <sensor-introduction-pofiles>`).

.. _background-data:

Collecting background data
^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. _bg-settings:
.. figure:: /_static/gui/bg_settings.png
    :figwidth: 40%
    :align: right

    Background settings for Envelope and IQ service

Especially when using Envelope data, taking a background measurement and subtracting it can be very useful.
To test the general idea, place one object in the line of sight of the sensor and start a new scan.
On the side-panel, scroll down to the **Processing settings** tab and expand it if necessary.
Wait for 50 frames (the current number of elapsed frames is shown in the bottom panel of the GUI) and click on **Use measured**.
This will subtract the average envelope signal of the first 50 frames of the current scan from every new frame.
You can also save the background and apply it to another scan by loading it.
You can either limit or subtract the background, selectable via the *Background mode* drop-down menu.
Now you can place a second object within the FOV of the radar and see the difference in response by enabling and disabling the background subtraction.

.. _bg-scan:
.. figure:: /_static/gui/bg_scan.png

    Difference in Envelope data with background subtraction turned on and off.

.. attention::
    Note, that we added the red plot to the top graph for better visualization.
    When using the GUI, you will only get one line-out at a time!

.. _replay-data:

Replay data
^^^^^^^^^^^
Within the **Scan controls** tab, you can find the **Replay** button and below, the setting for *Max buffered frames*.
When you do a scan, the GUI will keep this number of frames in the memory.
When you have stopped the scan, you can click **Replay**, to replay all buffered frames from the last scan.
Since the GUI only stores the unprocessed service data, you can change the processing in the *Processing settings* tab.

.. attention::
    When starting a new scan or selecting a different service or detector using a different service, the buffer is removed!

.. tip::
    When you have buffered data, you can freely switch between detectors and examples using the same service data type. You can collect data with the *IQ* example and replay it with the *Obstacle detection* for example!

.. _save-load:

Saving and loading data
^^^^^^^^^^^^^^^^^^^^^^^
When you have service data in the buffer, you can click **Save to file** to save this data to a file and load it at some later point for replaying.

When you save data, this information will be stored in file:

- service data (unprocessed) with time stamps
- information on saturation and dropped frames
- sensor settings
- detector and processing settings used when collecting data

Thus, when you load a previously saved scan, the GUI will switch to the detector that was used to collect that scan and restore the sensor settings and processing settings.
You will not be able to change any sensor settings, but you can change all processing settings and even switch to a different detector using the same service and replay the saved data.

.. attention::
    When you click on **New Measurement**, the loaded data gets removed from the buffer!
