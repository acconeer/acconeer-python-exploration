Detailed description of work flow steps
=======================================

Please note that there is a model status info box at the bottom of each tab, which shows the current status of the Keras model.
It will display, whether a model has been loaded or generated from training files and other useful information.
The reason is that once a model has been generated, certain options are grayed out as they should not be changed anymore.
Any change to these settings might render the feature frame generation, that the model is trained to predict, unusable.
These settings include the

- feature list
- sensor settings (all including sensors used)
- model layers (only if model is loaded from file)

Though, sometimes it is necessary to change the sensors used or other settings.
In that case, you can click "Unlock settings" at the right side of the info box.
This will allow changing the feature list and sensor settings and when you run or save the model, settings from the GUI will be used instead of the ones originally used to create the model.

When you start collecting data and until you are ready to train a model, you might want to minimize this box.

.. figure:: /_static/deep_learning/model_info_box.png
    :align: center

    Model info box at the bottom of each tab. You may minimize this box until you are ready to train or use a loaded model.

.. toctree::
   :maxdepth: 1
   :glob:

   select_service
   select_features
   feature_collection
   feature_inspection
   model_configuration
   model_training
   model_evaluation
