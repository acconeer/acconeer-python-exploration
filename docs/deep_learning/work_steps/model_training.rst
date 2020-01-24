.. _model-training:

Model training
==============

.. figure:: /_static/deep_learning/model_training_01.png
    :align: center

    Overview of the "Model training" tab.

Description of tab areas (roughly in order of work flow):

1. Start/stop training, configure training and validation options
2. List of unique labels found within loaded training data or model
3. Accuracy results
4. Loss results
5. Confusion matrix
6. Model info box

In order to train a model, you need to have training data loaded and the model initialized successfully.
Please refer to the instructions for :ref:`model-configuration` for details.
The default training and validation settings in area 1 work for most training scenarios.
Please refer to the `Keras documentation <https://keras.io/>`_ for description of individual settings.

If you want to save the best model after each epoch, check the **Save best iteration** box in area 6 and select the folder where you want the model saved.
This will save the model after an epoch, if its validation loss is lower then any previous epoch.
By default, :math:`20\%` (randomized) of the training data is used for validation at the end of each epoch.
You can choose to load specific files for validation or do no validation at all at the bottom of area 1.

When you click **Train**, training will start using all feature frames from all session files loaded with the unique labels shown in area 2.
The plots in area 3 and 4 will update after each batch (orange curve), and at the end of each epoch, validation will be updated (green curve).

By default, `Early dropout <https://keras.io/callbacks/#earlystopping>`_ is checked in area 1 and training will stop if the validation loss doesn't decrease over 5 epochs.
You can stop the training at any time by clicking the **Stop** button in area 1.

Once the training is done, the confusion matrix will be computed and displayed in area 5.
With large data sets, this might take a few seconds!
For a well trained model, all diagonal entries in the confusion matrix should be close to :math:`100\%` (indicated with green background color), i.e. the model predicts the training data correctly.
If the model is not trained properly, diagonal entries decrease, and off-diagonal entries increase (shown by orange to red background).

You may resume the training be clicking **Train** again.
You can load a model, then load training data and continue training the previous saved model as well.

.. attention::
  If your `optimizer <https://keras.io/optimizers/>`_ applies a dynamic learning rate (such as Adagrad), resuming training will revert to the original learning rate, i.e. likely start with a too large learning rate! You may want to reduce the default learning rate when resuming training.

When you have trained a model, you can save it in area 2 and/or advance to the next tab :ref:`model-evaluation` to test your model.
You may also use the saved model and run it stand-alone as described in :ref:`ml-stand-alone`.

Typical problems when training
------------------------------
a) The Accuracy doesn't converge to :math:`1`
b) The loss does not decrease
c) The loss decreases, but the validation loss increases
d) The loss first decreases, than suddenly increases

All these issues usually result in poor validation shown in the confusion matrix with many orange to red entries.
Most issues can be traced back to one of the following three problems:

1. The data cannot be trained, because the features frames you are creating are not optimal. You may want to change service and/ or feature settings. Typically a and b.
2. The data cannot be trained, because not enough feature frames have been collect. Collect more training data. Typically a and b.
3. The model is too large / has too many hidden layers (or too small) and the model is over-fitting. Try removing Conv2D, MaxPool2D layers and changing kernel size. Typically c and d.
