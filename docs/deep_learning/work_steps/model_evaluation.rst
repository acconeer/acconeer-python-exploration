.. _model-evaluation:

Model evaluation
================

.. figure:: /_static/deep_learning/model_evaluation_01.png
    :align: center

    Overview of the "Model evaluation" tab.

Description of tab areas (roughly in order of work flow):

1. Model info, load model (and unlock settings).
2. Connect to server and start measurement
3. Adjust feature collection mode
4. Current feature frame
5. Current prediction (in title) and history of predictions
6. Sensor service data history of 100 data frames

The main function of this tab is to live-test a previously trained model.
You may test any currently initialized model (indicated in area 1), whether trained or not.
Normally, you just have trained a model or loaded a previously trained model and want to live-test it now.
Before you start a measurement, you may have to change the sensors used (if more than one sensor).
The preferred method is to physically change the sensor attachment to match your model requirements.

But you can also click **Unlock settings** in area 1 and change sensor settings in the now enabled sensor settings below area 3.
If you do so, make sure to match the changed settings in the feature configuration!

.. attention::
    If you start a measurement with the settings unlocked, all settings are fetched from the GUI and settings stored with the model will be disregarded.

When you click **Start measurement**, feature frames will be collected based on the collection mode settings in area 3.
Feel free to change the settings, while the measurement is running.

The current feature frame will be displayed in area 4 and a history of predictions will be displayed in area 5.
A history of :math:`100` service data frames is shown in area 6.

.. tip::
  All features are stored in memory when you start a measurement (make sure the buffer size in area 2 is large enough).
  If you find that live-testing predicts feature frames incorrectly, you can stop the measurement and switch to the :ref:`feature-inspection` tab.
  There you can update the labels for incorrectly predicted features frames, store them in a new session file and include that session file when retraining the model.
