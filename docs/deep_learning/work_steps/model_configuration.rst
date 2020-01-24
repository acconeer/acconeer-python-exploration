.. _model-configuration:

Model configuration
===================

.. figure:: /_static/deep_learning/model_configuration_01.png
    :align: center

    Overview of the "Model configuration" tab.

Description of tab areas (roughly in order of work flow):

1. Model status area (Save/Load/Remove model data)
2. Add, update, reset layers
3. List of added layers and layer dimensions (only when model is initiated)
4. Layer controls (move up/down, remove, disable)
5. Load training data and start/stop/validate training
6. Training settings
7. Evaluation settings for training


.. attention::
    As explained in the introduction, it is important to keep in mind that once you start collecting feature frames, it is of paramount importance to **not** change any sensor or feature settings.
    Any such change may invalidate feature frame inter-compatibility and the possibility to properly train or use a model.

At this point, you should make sure that the model info area is expanded (area 1).
It shows important information about the current state and also allows to save and load models.
In area 3 you can see the current model layers.
You can add new layers with the drop-down menu in area 2, which will be added at the bottom of the current layer list.
Layers can be disable, removed or moved up and down with the controls on the right side of each layer (see area 4).
If you like, you can also save or load a layer configuration in area 2.
Layers are stored in an easy-to-read yaml file.
The default layer configuration for a 2D network is stored in `default_layers_2d.yaml <https://github.com/acconeer/acconeer-python-exploration/blob/master/gui/ml/default_layers_2d.yaml>`_.
You may start from this model configuration and adjust the model to your needs.
The default model is intended for larger feature frames (:math:`>100x50`).
Make sure to remove Conv2D and MaxPool2D layers if your feature frames are smaller.
Adjust the kernel size to roughly match the smallest "interesting" structures in your feature map and make sure that you do not reduce the layer size too much with MaxPool2D layers for smaller feature frames.
Finding optimum settings might involve an iterative approach with training and changing model layers.

.. attention::
    There is no sanity checking on your model layer configuration!
    Your model should end with a dense layer! The units value is disregarded and automatically set by the number of unique labels in your training files.

In most cases you will have saved several sessions to individual files, each containing labeled feature frames (using the same sensor and feature settings).
In area 5 you can load all relevant session files by clicking **Load training data**.
This will load all feature frames from all selected files, generate a list of unique labels and try to initiate the model based on your choice of layers.
You will be prompted with a list of found labels and, if present, a list of all files that failed loading.
If the layer configuration of the model is not compatible, an error message will be attached as well, indicating that the model has not been initiated.

.. figure:: /_static/deep_learning/model_configuration_02.png
    :align: center

    Message after loading session files, with 2 failed files and the model failed to initialize.

If the model didn't initialize properly, fix the error in the layer setup and click **Update model** in area 2.
When the model has been initialized successfully, the output dimensions of each layer will be updated in area 3.

.. attention::
    Note, if you change the layers after the model has been initialized, the model is not updated before you click **Update model**. If you click "Train" without updating the model, changes will be reverted automatically.

Before you start training your model by clicking **Train** in area 5, take a look at the training settings in area 6.
Usually, the default settings will work fine.
For details on the options please refer to the `Keras documentation <https://keras.io/optimizers/>`_.
You may want to save the model after each epoch; in that case check the **Save best iteration** box in area 6 and select the folder where you want the model saved.
Now, when you train, the model will be saved to file after each epoch if it has a lower validation loss than the previous epoch.

In area 7 you can change the settings for validation during training.
By default, :math:`20\%` (randomized) of the training data is used for validation at the end of each epoch.

When you are done with the model and training settings, you may click **Train**.
This will automatically advance to the next tab, :ref:`model-training`.


Adding new Keras layer
----------------------
If you want to add a layer to your model that is not present in the drop-down menu in area 2, you can add this by modifying the file `layer_definitions.py <https://github.com/acconeer/acconeer-python-exploration/blob/master/gui/ml/layer_definitions.py>`_.
You can only add existing `Keras layers <https://keras.io/layers/about-keras-layers/>`_!

.. code-block:: python
   :emphasize-lines: 11,43,44

    import numpy as np
    from keras.layers import (
        BatchNormalization,
        Conv1D,
        Conv2D,
        Dense,
        Dropout,
        Flatten,
        GaussianNoise,
        MaxPool2D,
        # Add the missing Keras layer class here
    )


    def get_layers():
        layers = {
            "conv1d": {
                "class_str": "Conv1D",
                "class": Conv1D,
                "dimensions": 1,
                "params": {
                    "filters": [32, int, [0, np.inf]],
                    "kernel_size": [8, int, [1, np.inf]],
                    "padding": ["drop_down", ["same", "None", "even"]],
                    "activation": ["drop_down", ["relu"]],
                },
            },
            "conv2d": {
                "class_str": "Conv2D",
                "class": Conv2D,
                "dimensions": 2,
                "params": {
                    "filters": [32, int, [0, np.inf]],
                    "kernel_size": [(2, 2), int, [1, np.inf]],
                    "strides": [(1, 1), int, [0, np.inf]],
                    "padding": ["drop_down", ["same", "even", "None"]],
                    "activation": ["drop_down", ["relu"]],
                },
            },

            ...

            # Add the same structure as above and add the info corresponding to the newly
            # added layer.
