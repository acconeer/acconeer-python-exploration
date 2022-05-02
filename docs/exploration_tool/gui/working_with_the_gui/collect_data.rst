.. _collect-data:

Collect data
============
The Acconeer Exploration Tool GUI makes it very easy to collect data, be it for evaluation, testing or in-depth detector tuning or development.
At the heart of the data collection are the functions for starting and stopping a scan and saving and loading the data that has been collected in this way.

.. attention::
    The GUI never stores processed data, only the original service data, including all sensor and detector settings. Whenever you replay data (saved or buffered), the processing is always redone on the original sensor data.

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

    Background settings for Envelope service

Especially when using Envelope data, taking a background measurement and subtracting it can be very useful.
To test the general idea, place one object in the line of sight of the sensor.
On the side-panel, scroll down to the **Processing settings** tab and expand it if necessary.
You can either limit or subtract the background, selectable via the **Background mode** drop-down menu.
For this example, we will subtract.

Scroll down a bit further, and you come across the **Calibration management** section (New in **v4**).
This section allows you to have full control over your recorded background data, *or calibrations*.

.. _calibration-management:
.. figure:: /_static/gui/no_calibration.png
    :figwidth: 60%
    :align: center

    The Calibration management section

The elements in the blue rectangle controls the saving and loading of a calibration.

* **Load calibration**: Lets you load a calibration that you have recorded before
* **Save calibration**: Lets you save the current calibration (loaded from file or produced by the Envelope service)
* **Clear calibration**: Lets you delete the current calibration and start with a clean slate.

The elements in the green rectangle controls the calibration's interaction with the current processor (the Envelope service for example)

* **Apply calibration**: Sends the current calibration to the processor (Can be seen in the plots)
* **Auto apply calibration**: Automatically applies the calibration to the processor as soon as it's ready (After 50 frames for example).
* **Clear calibration**: Resets the processor's calibration. (In addition to deleting the current calibration, as mentioned before.)

.. attention::
    Calibration changes within a measurement are not saved. Altering calibration during recording is **not recommended**.

With this in mind, go ahead and start a new measurement.
Wait for 50 frames (the current number of elapsed frames is shown in the bottom panel of the GUI)

Once the 50 frames have passed, the calibration can be handled from the **Calibration management** section:

.. figure:: /_static/gui/session_calibration.png
    :figwidth: 60%
    :align: center

    Calibration section with an unsaved calibration

While still measuring, press **Apply calibration**.
This will subtract the average envelope signal of the first 50 frames of the current scan from every new frame.

You can also save the background and apply it to another scan by loading it:

.. figure:: /_static/gui/saved_calibration.png
    :figwidth: 60%
    :align: center

    Calibration section after **Save calibration** is pressed

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
