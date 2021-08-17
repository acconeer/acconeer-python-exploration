.. _deep-learning-introdution:

Overview of the deep learning interface
=======================================
Acconeer's deep learning interface (DLI) gives you the possibility to quickly collect data for training and evaluating deep learning models.
Using our DLI, you should be able to evaluate your use-case within a few hours, without writing a single line of code; all steps required to train and live-test a model are integrated into the DLI.
It uses Keras as front-end for Tensorflow and the main requirement is to have a basic understanding of radar and how you could utilize our radar signals to realize your use-case.
Common use-cases are gesture detection for control of electronic devices or material detection for use in robotics.
We have a dedicated repository for deep learning examples on our `GitHub <https://github.com/acconeer/acconeer-deep-learning-examples>`_ page, where you can get ideas of how to approach your specific use-case.

For our deep learning examples and in general, the basic idea is to convert the sensor data into a 1 or 2 dimensional arrays, much like ordinary images.
For training a Keras model, each of these images is tagged with a label, such as "move_hand_to_left" or "carpet".
Once the model has been trained on these images, we can use the model to predict untagged images.

.. figure:: /_static/deep_learning/ml_overview.png
    :align: center

    A schematic depiction of the general data flow / work steps for a deep learning project using our radar.

Independent of the use-case or the particular model, the following steps are required to generate a working Keras model ready for prediction of untagged images:

1. Choose a service (Envelope, IQ or Sparse)
2. Configure sensor settings (e.g. update rate and range)
3. Choose which features should be extracted from the data (e.g. FFT, peak or range segment)
4. Collect data for each model class (e.g. "move_hand_to_left" or "carpet" depending on what should be predicted)
5. Inspect collected data (e.g. remove  or relabel data points)
6. Configure a Keras model (either use the predefined model or define layers yourself)
7. Load all collected data and train the model
8. Evaluate the model with live ("unseen") data
9. Export the model for implementation in your own software environment

The DLI covers steps 1. through 8. and for step 9. we offer an example how to use a model generated with the DLI in a python environment.
In order to start the DLI you add '- ml' to the usual command to::

    python gui/main.py -ml

Once started, you can see that the GUI has a tab for each of these work-flow steps (except step 1 and 2).

.. figure:: /_static/deep_learning/ml_front.png
    :align: center

    A screenshot of the tabs in Acconeer Exploration Deep Learning Interface


Data-flow and Python framework
------------------------------
The deep learning interface works on-top of two main python files, `feature_processing.py <https://github.com/acconeer/acconeer-python-exploration/blob/master/gui/ml/feature_processing.py>`_ and `keras_processing.py <https://github.com/acconeer/acconeer-python-exploration/blob/master/gui/ml/keras_processing.py>`_.
There are two more files, `feature_definitions.py <https://github.com/acconeer/acconeer-python-exploration/blob/master/gui/ml/feature_definitions.py>`_ and `layer_definitions.py <https://github.com/acconeer/acconeer-python-exploration/blob/master/gui/ml/layer_definitions.py>`_, in which the calls to the feature calculation and model layer construction are stored, respectively.
The GUI accesses all required functions through these two files, which means, you can write your own code around these files if you prefer not using the GUI as front-end.
Otherwise, the GUI makes sure that the data format and flow is correct and helps you focus on evaluating your particular use-case rather than writing your framework.

In the following graph you can see a schematic depiction of the general data flow, where the **feature_processing.py** converts the sensor service data to feature frames either for training a model or for prediction with a model.
All Keras/Tensorflow related functionality, such as training and predicting, is taken care of by **keras_processing.py**.

.. graphviz:: /graphs/ml_framework.dot
   :align: center

.. _ml_data_flow_overview:

.. _ml-stand-alone:

Stand-alone use of model
------------------------
Once you have trained a model using the GUI and saved it, you may use this model outside the GUI using our `stand_alone.py <https://github.com/acconeer/acconeer-python-exploration/blob/master/gui/ml/stand_alone.py>`_.

All you need to do is, create a **feature processor**, which you feed the sensor :ref:`services` data.
This processor returns feature frames, which you can predict with an instance of the **keras processor**:

.. code-block:: python
    :emphasize-lines: 1,6,10,15,22,26,34

    # Import modules
    import keras_processing as kp
    import feature_processing as feature_proc

    ...
    # Initiate keras processor to load model:
    keras_proc = kp.MachineLearning()
    model_data = keras_proc.load_model(filename)

    # Extract model/feature settings from loaded model
    config = model_data["sensor_config"]
    feature_list = model_data["feature_list"]
    frame_settings = model_data["frame_settings"]

    # Initiate feature processor:
    feature_process = feature_proc.FeatureProcessing(config)
    feature_process.set_feature_list(feature_list)
    feature_process.set_frame_settings(frame_settings)

    ...

    # Initiate the service scan
    while not interrupt_handler.got_signal:
        info, sweep = client.get_next()

        # Format sweep data and send it to feature processor
        data = {
            "sweep_data": sweep,
            "sensor_config": config,
            "session_info": session_info,
        }
        ml_frame_data = feature_process.feature_extraction(data)

        # Extract feature map and predict it:
        feature_map = ml_frame_data["current_frame"]["feature_map"]
        complete = ml_frame_data["current_frame"]["frame_complete"]
        if complete and feature_map is not None:
            predict = keras_proc.predict(feature_map)[0]
            label = predict["prediction"]
            confidence = predict["confidence"]
            print("Prediction: {:10s} ({:6.2f}%)\r".format(label, confidence * 100), end="")


Definitions
-----------
Throughout this documentation and within the DLI, several names and acronyms are used to describe elements required for training and evaluating a Keras model with Acconeer's radar sensor:

Feature
^^^^^^^
A feature refers extracting information from the sensor service data via any means of post-processing.
This can be as simple as direct copy of the service data (i.e. no processing).
More common examples of post-processing are:

- cutting / slicing of data
- peak detection
- FFT
- averaging/variance over time
- feeding data into one of our examples and using its output as feature


Feature frame
^^^^^^^^^^^^^
You may choose to extract several features at once from the service data.
When you do that, all features will be stacked vertically to form one large array, the feature frame.
The feature frame can be a 1D or 2D array, depending on the type of features you select.
See :ref:`select-features` and :ref:`feature-collection` for examples.

Frame time
^^^^^^^^^^
The frame time :math:`t_f` defines the length of a feature frame.
With a given update rate :math:`f`, the number :math:`N_f` of (sensor) data frames per feature frame is calculated as

.. math::
   N_f = t_f * f

Layer
^^^^^^
A Keras/Tensorflow model consists of a number of different layers, e.g. a convolution layer or dense layer.
For each deep learning problem, an optimization of the layer structure might be necessary.

Collection mode
^^^^^^^^^^^^^^^^
The collection mode specifies the method of triggering the calculation of a feature frame.
We support auto-detection, manual and continuous (rolling and non-rolling), but you may add your own trigger method.
The details of each method are explained in the step-by-step documentation.

Detection volume
^^^^^^^^^^^^^^^^
The sensor has a field of view (FOV) of around :math:`60^{\circ}-80^{\circ}` without a lens (see :ref:`sensor-intro`).
The cone-shaped volume spanned by the FOV with a length of the scan range forms the detection volume.
Naturally, you need to have your object for prediction within that detection volume.
Please keep in mind that the radar output power decreases towards larger emission angles and thus any reflected signal.

Label
^^^^^
Internally, we make use of Keras/Tensorflow's categorical feature, which describes all possible prediction outcomes in a binary class matrix.
A label is a string representation for an individual row in the binary class matrix, e.g. "carpet", "hand_moving_to_left" or "XY123".
When a prediction is performed, the outcome is converted from this binary class matrix to the corresponding label.
