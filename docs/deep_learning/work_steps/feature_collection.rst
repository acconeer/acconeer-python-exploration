.. _feature-collection:

Feature collection
==================
.. figure:: /_static/deep_learning/collect_feature_01.png
    :align: center

    Overview of the "Collect features" tab.

Description of tab areas (roughly in order of work flow):

1. Type label name
2. Configure feature collection mode
3. Start/Stop measurement, or load scan data from file for labeling
4. Current feature frame
5. History of sensor service data
6. Load session or save session with labeled feature frame data
7. Select list of session files for batch processing (e.g. for relabeling or changing feature settings)

At this point you should have chosen all the features you want to extract from the service data and confirmed that the feature extraction works as expected (by clicking **Test extraction** on the previous tab).

.. attention::
    Once you start collecting features for training a new model, you must not change settings for the features, the sensor or the frame time! Any such change might result in collected feature frames not being compatible with each other.

Labeling
--------
Let's assume you want to create a model to distinguish between the following labels representing movement of your hand: "up_down", "to_left"  and "to_right".
This means you will need to collect feature frames for all three labels and use those feature frames to train your model.
Starting with any of your labels, type the label name into the text box in area 1.
All features collected after clicking "Start Measurement" will be tagged with that label.
Note that you can change the label for collected feature frames in the :ref:`feature-inspection` tab.

Collection mode
---------------
The collection mode defines when to start collecting and extracting a feature.
When you click **Start measurement** in area 3, sensor service data will be collected continuously, but you still need to decide when to trigger a new feature frame.
Depending on your use case, different collection modes suite better than others.

    .. figure:: /_static/deep_learning/collect_feature_02.png
        :align: center

        Feature collection mode options (area 2)

By default, we offer 3 different collection modes:

+----------------------+-----------------------------------------------------------------------+
| **Collection mode**  | **Use case example**                                                  |
+======================+=======================================================================+
| | Auto               | | Isolated gestures, where you leave the detection volume             |
|                      | | between individual gestures                                         |
+----------------------+-----------------------------------------------------------------------+
| | Single             | | An external trigger marks the beginning of an isolated event        |
|                      | | (usually only used in special cases, where other modes fail)        |
+----------------------+-----------------------------------------------------------------------+
| | Continuous         | | Continuous gestures, where you don't leave the detection volume     |
|                      | | Also applies to material detection                                  |
+----------------------+-----------------------------------------------------------------------+

Often it is necessary to use a different collection mode for collecting labeled feature frames and for using the trained model.
You may change between different collection modes or change collection mode settings at any time, even while scanning.

Auto detection
^^^^^^^^^^^^^^
With the auto collection mode, you can choose between presence based and feature frame based detection of feature frames.

Presence based detection:
    With the presence based detection, motion triggers the start of a new feature frame.
    When using Envelope or IQ, a simple algorithm keeps track of the peak amplitude and sends a trigger when a certain threshold is passed.
    When using Sparse, the "Presence detection (Sparse)" detector is running in the background and sending a trigger when presence above a certain threshold is detected.

    You can set 3 different settings:

    1. **Threshold**: Trigger is send when normalized motion/amplitude above threshold is detected. Typically a working threshold is between 1.2 and 3.0. You can change the threshold setting while scanning to find an optimum value. Check the motion score close to area 4 to see the current value.
    2. **Offset**: Once a trigger is send the extraction of a feature frame is offset by this many sensor data frames. For example, with an offset of 15, 15 sensor data frames are kept in memory, so that the feature frame starts 15 data frames ago once a trigger is has been sent. Typical values are around 10 to 30, but with higher sensor update rates the offset usually increases further.
    3. **Dead Time**: Specifies the dead time between triggers. With a dead time of 10, no trigger will be sent for 10 sensor data frames after the last feature frame has been finished. If you have a sensor update rate of 50 that means no trigger will be sent for :math:`0.2\,\text{s}` after the last feature frame ended.
Feature based detection:
    With feature based detection, feature frames are collected continuously and analyzed for data their data contend.
    Unless the following conditions are met, the feature frames are discarded:

    1. The normalized sum of the left and right side of the feature frame, defined by the **Offset**, deviate by less than :math:`10\%`. The left side spans from 0 to offset, while the right side spans (end - offset) to end of the feature frame.
    2. The center of the image, i.e. the data between the left of the right side, has normalized sum that is **Threshold** times larger than the left and right side together.

    In other words, a feature frame is only accepted, if the center of the feature frame contains information, while the sides do not!
    Please note that the **Dead time** option has no effect.

Single detection
^^^^^^^^^^^^^^^^
Click the button **Trigger** to start collecting a new feature frame.

Continuous detection
^^^^^^^^^^^^^^^^^^^^
You can choose between rolling and non-rolling.
With rolling enabled, features will be collected after each other, i.e. once a feature frame is done, a new one is started immediately.
With rolling disabled, a new feature frame will be started with each new sensor data frame.

Adding your own collection mode
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
While you can easily add your own collection mode, adding collection modes to the GUI automatically is not possible (like it is possible with features or model layers).
You need to modify the function call auto_modetion_detect() in the `feature_procssing.py <https://github.com/acconeer/acconeer-python-exploration/blob/master/gui/ml/feature_processing.py>`_ file.
Make sure you return "True", when you want to send a trigger, otherwise return "False".

.. code-block:: python

    def auto_motion_detect(self, data, feature_based=False):
        detected = False

        if feature_based:
            wing = self.auto_offset
            if len(data.shape) == 2:
                if wing >= (self.frame_size / 2):
                    self.motion_score_normalized = "Reduce offset!"
                    detected = True
                else:
                    center = np.sum(data[:, wing:-wing]) / (self.frame_size - 2 * wing)
                    left = np.sum(data[:, 0:wing]) / wing
                    right = np.sum(data[:, -(wing + 1):-1]) / wing
                    if right == 0 or left == 0:
                        self.motion_score_normalized = 0
                        return detected
                    if left / right > 0.9 and left / right < 1.1:
                        self.motion_score_normalized = 2 * center / (left + right)
                        if self.motion_score_normalized > self.auto_threshold:
                            detected = True
            else:
                self.motion_score_normalized = "Not implemented"
                detected = True
            return detected

        num_sensors = data["sweep_data"].shape[0]
        sensor_config = data["sensor_config"]
        mode = sensor_config.mode

        if mode == Mode.SPARSE and not SPARSE_AUTO_DETECTION:
            if self.sweep_counter <= 10:
                print("Warning: Auto movement detection with spares not available.")

        if mode == Mode.SPARSE and SPARSE_AUTO_DETECTION:
            if self.motion_processors is None:
                self.motion_config = presence_detection_sparse.get_processing_config()
                self.motion_config.inter_frame_fast_cutoff = 100
                self.motion_config.inter_frame_slow_cutoff = 0.9
                self.motion_config.inter_frame_deviation_time_const = 0.05
                self.motion_config.intra_frame_weight = 0.8
                self.motion_config.intra_frame_time_const = 0.03
                self.motion_config.detection_threshold = 0
                self.motion_config.output_time_const = 0.01
                self.motion_class = presence_detection_sparse.PresenceDetectionSparseProcessor
                motion_processors_list = []

        ...

Collecting feature data
-----------------------
In area 3 you can either Start a new measurement or load previously recorded sensor data, i.e. recorded data from the standard GUI, which does not contain any information about deep learning settings.
When you stop a measurement, the sensor service data, all feature frames and the feature settings are stored in buffer.


.. attention::
    Please note that when you start a measurement:

        - the data buffer is set to unlimited!
        - the buffer is cleared including any previously extracted feature frames!
        - with "Replaying", all previously extracted feature frames are cleared!

When you start a measurement, service data will be collected continuously and the the history (last 100 data frames) is shown in area 5.
As discussed above, the generation of feature frames is based on the **Collection mode** you have the chosen.
In the bottom left corner of the feature frame graph (area 4), the status of the feature frame generation is displayed.
In case of single motion detection triggering, "Waiting.. (Motion score: x.xx)" is shown, until a trigger is received (where the motion score is only shown in the latter).
When a trigger is received or for continuous detection, it will show "Collecting...".
Above that, a counter shows the number of generated feature frames.

Saving and loading feature frame data
-------------------------------------
When you stop a measurement and want to save the feature frames for training a model later, click **Save session** in area 6.
This will save all sensor service data, all feature frames with their labels and all sensor/feature settings.
You may store feature frames with different labels in the same file.
The GUI will auto-generate a file name, which includes the current label, but the file name can by arbitrary!
The labels are stored with the feature frames and not read from the file name!

Each session file contains a dictionary in the following format:

.. graphviz:: /graphs/ml_data_structure.dot
   :align: center

.. _ml_data_structure:

You may load a previously saved session at any time by clicking **Load session**, which will:

- recover your feature settings (i.e. overwrite your current settings!)
- restore the sensor settings
- load the sensor service data into the buffer
- recover calibration data used for feature generation

Now, you can change the feature / frame settings or the collection mode and when you clicked "Replay buffered", feature frames will be generated from the saved sensor service data, using the updated settings.

.. attention::
    You need to save the session again, if you want to keep any changes you do after loading a session!

Batch processing saved session data
-----------------------------------
In some cases you may have to change settings on several saved sessions.
In order to do so, you can click on **Batch load** in area 7.
There you can select multiple session files at once.
Please note, that nothing is actually loaded or restored at this point, it will just generate a list of session files to process.
When you click **Process batch**, the GUI will ask you whether to keep labels or overwrite the labels and then go through this list reprocessing each file with the current GUI settings and save it to a new file appending "batch_proccesed" to the original file name.
If you chose to overwrite the labels, all feature frames from all selected files will be given the new label.
