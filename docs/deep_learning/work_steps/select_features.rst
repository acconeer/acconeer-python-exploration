.. _select-features:

Select features
===============
.. figure:: /_static/deep_learning/select_feature_01.png
    :align: center

    Overview of the "Select features" tab.

Description of tab areas (roughly in order of work flow):

1. Add new feature or test feature extraction
2. List of enabled features and their options and output
3. Select for which sensor the feature should be extracted
4. Status box indicating possible mismatch of feature and sensor settings
5. Match feature settings to sensor settings or vise versa
6. Size and position of individual features (color of rectangle matches color of feature name in area 2) and live display of feature when "Test extraction" is running

In this step you should select the features you would like to extract from the sensor data and configure their options and output.
First, you should add a feature from the drop down menu in area 1.
This feature will then be added to the list of features shown in area 2 of the tab.
All features have a start and stop option and if available, additional options specific to the particular feature.
If more than one output from the feature is available, you can select which outputs you want by ticking the corresponding check box.
Further to the right, you can choose for which sensor this feature should be extracted.

.. tip::
    You can add the same feature as many times as you want and change parameters for each instance individually.
    For example, you can add the "Range segment" feature and use different start and stop values for different or the same sensor.

.. attention::
    You must not add features of different dimensions or for different sensor data service types.
    The status box at point 4 will indicate any such mismatch!

In area 4 you can define the feature frame time.
Together with the sensor update rate, this defines how many sensor data frames will be used to construct one feature frame.
At the moment, all features return either a single float value or a 1D array of floats for each sensor data frame.
Thus, if you define a frame time of :math:`0.8\,\text{s}` and have a sensor update rate of :math:`60\,\text{Hz}` your feature frame will consist of features from 48 sensor data frames.

.. tip::
    Make sure that whatever you want to predict, happens over a shorter period in time than your feature frame time!
    For material detection, the frame time can be rather short, but for gesture detection you should consider some extra time to account for people performing gestures at different speeds.

Whenever you have a mismatch between the feature settings and the sensor settings, it will be displayed in area 5.
Common mismatches are start or end range of the feature exceeding the sensor scan range or having a feature which requires a different type of sensor service data.
To quickly fix these type of errors, you can on either click on "Sensor to Feature" or "Feature to Sensor" in area 6.
Note that if you write the sensor settings back to the feature by clicking "Sensor to Feature", all available sensors will be selected for all features.

At this point, you can see a preview of the feature map (created by vertically stacking all features) in area 7.
Each feature is represented by a square with corresponding size and color matching the list in area 2.
If you want test how the feature looks with actual data, you can click on "Test extraction", provided you are connected to a sensor.
You may also load data and click "Replay buffered".
This will create a feature map based on your settings and overlay them with rectangles.
You can change most feature settings while running, and the changes are applied directly.
When you are happy with the settings you may proceed to the next tab.


Adding your own features
------------------------
You may not find a feature that extracts the information that you would like to get.
When that happens, you can easily add your own feature by changing the file `feature_definitions.py <https://github.com/acconeer/acconeer-python-exploration/blob/master/gui/ml/feature_definitions.py>`_.

At the beginning of this file you can find a function called "get_features()".
Just add a new element for your new feature in the same way at the end of that function.

.. code-block:: python
   :emphasize-lines: 10,11,12,13,14,15

    def get_features():
        features = {
            "sweep": {
                "name": "Range segment",
                "class": FeatureSweep,
                "model": "2D",
                "data_type": Mode.ENVELOPE,
            },
    ...
            "your_feature": {
                "Name": Your Feature Name,
                "class": YourFeatureClass,
                "model": "2D" # or 1D if your output is a single float
                "data_type": Mode.ENVELOPE # Mode.IQ or Mode.SPARSE
            },
        }

Next, you need to add the code that performs your custom feature extraction in a class with the same name as you entered with the dictionary key "class" (in the above example that is "YourFeatureClass").
It is important that this class has the same structure as the other classes!
The GUI will automatically add your new feature to the drop-down list and add boxes for all options and data outputs you have defined.
Below you can see the code used to generate the feature called "Range segment" with a class name of "FeatureSweep".

.. code-block:: python
   :emphasize-lines: 3,7,8,21,22,28,29,38,54,55,56,57

    class FeatureSweep:
        def __init__(self):
            # Output data of your feature
            self.data = {
                "segment": "Segment",
            }
            # Options for your feature --> text, value, limits, type
            # Must have "Start" and "Stop"!
            self.options = [
                ("Start", 0.2, [0.06, 7], float),
                ("Stop", 0.4, [0.06, 7], float),
                ("Down sample", 8, [1, 124], int),
                ("Flip", False, None, bool),
            ]

        def extract_feature(self, win_data, win_params):
            try:
                sensor_idx = win_params["sensor_idx"]
                dist_vec = win_params["dist_vec"]
                options = win_params["options"]
                # You can access the different service data types with
                # "env_data", "iq_data" and "sparse_data"
                arr = win_data["env_data"][sensor_idx, :, :]
            except Exception as e:
                print("env_data not available!\n", e)
                return None

            # Do some sanity checks on start and stop, the supplied "dist_vec" is a vector
            # mapping indices to mm distance
            data_len, win_len = arr.shape
            start = distance2idx(options["Start"] * 1000, dist_vec)
            stop = distance2idx(options["Stop"] * 1000, dist_vec)
            downsampling = int(max(1, options["Down sample"]))

            if start >= stop:
                return None

            # You need to return a dict with the same entries as defined in the __init__ call
            if options["Flip"]:
                data = {
                    "segment": np.flip(arr[start:stop:downsampling, :], 0),
                }
            else:
                data = {
                    "segment": arr[start:stop:downsampling, :],
                }

            return data

        def get_options(self):
            return self.data, self.options

        def get_size(self, options=None):
            # If you know how to calculate the height of yout feature, add the code here,
            # otherwise return 1. If the calculation is incorrect, the rectangle showing the size
            # in the select_features tab will be wrong, but that is not a problem. It is only a
            # visual aid!
            if options is None:
                return 1
            try:
                start = float(options["Start"])
                stop = float(options["Stop"])
                downsample = int(options["Down sample"])
                size = (stop - start) * 100 * 124 / downsample / 6 + 1
            except Exception as e:
                print("Failed to calculate feature hight!\n ", e)
                return 1
            return int(size)

The data send to the class consisits of two different dictionaries, **win_data** and **win_params**.
The structure of these dictionaries is as follows:


1. **win_data**:
    +---------------+-----------------------------------------------+-----------------------+
    | **entry**     | **data dimension**                            | required **Services** |
    +===============+===============================================+=======================+
    | 'iq_data'     | [sensor_index, distance, frame_time]          | IQ                    |
    +---------------+-----------------------------------------------+-----------------------+
    | 'env_data'    | [sensor_index, distance, frame_time]          | IQ or Envelope        |
    +---------------+-----------------------------------------------+-----------------------+
    | 'sparse_data' | [sensor_index, sweeps, distance, frame_time]  | Sparse                |
    +---------------+-----------------------------------------------+-----------------------+

    Please note that the data is only available if you have selected the corresponding service.
    Please keep in mind that a Sparse sensor frame consists of several sweeps for each distance points and thus has one extra dimension!
2. **win_params**:
    +------------------+------------------------------------------------------------------------------------+
    | **entry**        | **description**                                                                    |
    +==================+====================================================================================+
    | 'options'        | options specified in the feature definition                                        |
    +------------------+------------------------------------------------------------------------------------+
    | 'dist_vec'       | array mapping sweep data indices to distance in mm                                 |
    +------------------+------------------------------------------------------------------------------------+
    | 'sensor_config'  | sensor_config object containing all sensor parameters                              |
    +------------------+------------------------------------------------------------------------------------+
    | 'session_info'   | session_info object containing addition information about the current scan session |
    +------------------+------------------------------------------------------------------------------------+


Adding a processing example as feature
--------------------------------------
You can also include output from one of our processing examples as a feature.
As an example, we have added a feature called "Presence Sparse", which sends the service data to the presence sparse detector and uses the detector output as data for the feature.
If you want to add another detector, please add the corresponding import at the beginning of the the file:

.. code-block:: python
   :emphasize-lines: 4

    try:
        sys.path.append(os.path.join(os.path.dirname(__file__), "../../"))
        from examples.processing import presence_detection_sparse
        # Add the processing example you want here!
    except Exception as e:
        print("Could not import presence detector:\n", e)
        DETECTORS_SUPPORTED = False
    else:
        DETECTORS_SUPPORTED = True

You can look at the class FeatureSparsePresence to see how to implement the code for the processing.
The main difference to the feature class above is that you need to initiate the detector at the beginning and send the service data to the detector afterwards.

.. code-block:: python
   :emphasize-lines: 13,21,50,68,75

    class FeatureSparsePresence:
        def __init__(self):
            # output data
            self.data = {
                "presence": "Presence",
            }
            # text, value, limits
            self.options = [
                ("Start", 0.2, [0.06, 7], float),
                ("Stop", 0.4, [0.06, 7], float),
            ]

            # Create variables for detectors
            self.detector_processor = None
            self.history = None

        def extract_feature(self, win_data, win_params):
            try:
                num_sensors = win_data["sparse_data"].shape[0]
                if self.detector_processor is None:
                    # Add entry for each sensor to detector list
                    self.detector_processor = [None] * num_sensors
                    self.history = None
                sensor_config = win_params["sensor_config"]
                session_info = win_params["session_info"]
                sensor_idx = win_params["sensor_idx"]
                dist_vec = win_params["dist_vec"]
                options = win_params["options"]
                arr = win_data["sparse_data"][sensor_idx, :, :, :]
            except Exception as e:
                print("sparse_data not available!\n", e)
                return None

            point_repeats, data_len, win_len = arr.shape
            data_start = dist_vec[0]
            data_stop = dist_vec[-1]

            # dist_vec is in mm
            start = max(data_start, options["Start"] * 1000)
            stop = min(data_stop, options["Stop"] * 1000)

            if start >= data_stop:
                return None

            start_idx = np.argmin((dist_vec - start)**2)
            stop_idx = np.argmin((dist_vec - stop)**2) + 1

            stop_idx = max(start_idx + 1, stop_idx)

            # Initiate the detector here!
            if self.detector_processor[sensor_idx] is None:
                detector_config = presence_detection_sparse.get_processing_config()
                detector_config.detection_threshold = 0
                detector_config.inter_frame_fast_cutoff = 100
                detector_config.inter_frame_slow_cutoff = 0.9
                detector_config.inter_frame_deviation_time_const = 0.05
                detector_config.intra_frame_time_const = 0.03
                detector_config.intra_frame_weight = 0.8
                detector_config.output_time_const = 0.01
                detector_handle = presence_detection_sparse.PresenceDetectionSparseProcessor
                self.detector_processor[sensor_idx] = detector_handle(
                    sensor_config,
                    detector_config,
                    session_info
                )
                self.detector_processor[sensor_idx].depth_filter_length = 1

            # Send service data to detector and receive its output
            detector_output = self.detector_processor[sensor_idx].process(arr[:, :, 0])
            presence = detector_output["depthwise_presence"]

            if self.history is None:
                self.history = np.zeros((num_sensors, len(presence), win_len))

            # Add desired output from detector to the feature and return it
            self.history[sensor_idx, :, :] = np.roll(self.history[sensor_idx, :, :], 1, axis=1)
            self.history[sensor_idx, :, 0] = presence

            data = {
                "presence": self.history[sensor_idx, start_idx:stop_idx, :],
            }

            return data

        def get_options(self):
            return self.data, self.options

        def get_size(self, options=None):
            if options is None:
                return 1
            try:
                start = float(options["Start"])
                stop = float(options["Stop"])
                size = int(np.ceil((stop - start) / 0.06)) + 1
            except Exception as e:
                print("Failed to calculate feature hight!\n ", e)
                return 1
            return int(size)
