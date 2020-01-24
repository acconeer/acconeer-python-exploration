.. _feature-inspection:

Feature inspection
==================
.. figure:: /_static/deep_learning/feature_inspection_01.png
    :align: center

    Overview of the "Feature inspection" tab.

Description of tab areas (roughly in order of work flow):

1. Current label name (can be edited)
2. Current feature frame and first sensor service data frame of current feature frame
3. Image of current feature frame
4. Update/remove feature frames
5. Load / save session data
6. Create / show calibration

While this tab is optional, it is highly recommended to inspect feature frames collected in the previous :ref:`feature-inspection` tab, before you use them to train a model.
The basic idea is to remove unsuitable feature frames or create a calibration if necessary.


Updating / adding / removing features
-------------------------------------
.. attention::
    Any change you make are only in temporary.
    You must click **Save session** to write the updated session data to file and make your changes permanent!

Whenever you have buffered data available, you can switch to this tab to inspect all collected feature frames.
Buffered data may be generated at several points in the work-flow and can, regardless of its origin, always be inspected here:

- when you click "Test extraction" in the :ref:`select-features` tab
- when you start or replay data in the :ref:`feature-collection` tab
- when you evaluate a model in the :ref:`model-evaluation` tab
- when you click "Load session" in this or any of the two previous tabs

In area 1, the label of the currently shown feature frame is shown.
You may change the label and write it back to all currently loaded feature frames by clicking **Write label to all frames**.
If you only want to change the label for the current feature frame, click **to current frame** in area 4.
You can cycle through all available feature frames in area 2 using the bottom slider.
Keep in mind, that a session always stores both, the individual feature frames as well as the original untouched sensor data.
When you select a new feature frame, the top slider will jump to the index of the first sensor data frame of that particular feature frame; at this point the feature frame is displayed as stored and not recalculated from the original data!

Sometimes it happens that a trigger has been sent to early or to late and you want to change the start of the feature frame generation.
Here, you can use the top slider to change at which sensor data frame the feature frame should start.
The feature frame will then be recalculated from the original, untouched sensor data with the updated start position!
In area 4 you can now choose to write the changes either:

- to the current frame
- to a new frame (keeping the old one)

You may also remove the current frame completely.

The **Data augmentation** button in area 4 allows you to create new feature frames around existing ones by specifying a list with offsets.

.. figure:: /_static/deep_learning/feature_inspection_02.png
    :align: center

    Data augmentation list input.

You may choose to augment only the current or all feature frames.
The augmented feature frames will inherit the label from the original feature frame.

.. attention::
    Some features may have a long term memory, i.e. depend on sensor data frames from before the current trigger.
    One such feature is the **Presence Sparse**.
    If you use data augmentation or change the start of the feature frame in area 2, the recalculated feature frame may be incorrect, since no history is generated!
    (Future updates will include the option to generate history for these cases.)

Feature frame calibration (experimental)
----------------------------------------
This part of the deep learning interface is still WIP and only basic/limited functionality is available at this point.
In some cases, you may add features in the :ref:`select-features` tab that have largely different values.
Training on features with strongly varying values is likely to fail and a calibration/normalization is necessary.
In other cases the value for features may change depending on your sensor integration and you will need a way implement a calibration for these changes.
At the moment, we support generation of a calibration/normalization frame by loading a session file in area 5.
After selecting a file, the average of all saved feature frames in this file will be calculated and displayed in a new window.
You can then choose to either take or discard this calibration frame.
If you choose to take the displayed calibration frame, all new feature frames will be divided by this calibration frame.
No changes will be made to currently buffered feature frames!
The buttons in area 6 will change to **Clear calibration** and **Show calibration** to either remove or display the current calibration frame, respectively.

When you save session data, the calibration frame will be attached to it.
Thus, when you load session data, the calibration frame will also be restored.

.. figure:: /_static/deep_learning/feature_inspection_03.png
    :align: center

    Calibration frame generation.
