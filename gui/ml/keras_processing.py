import os
import sys
import traceback

import numpy as np
import tensorflow as tf
from keras import backend as K
from keras import optimizers as Opt
from keras.callbacks import Callback, EarlyStopping
from keras.layers import (
    Activation,
    BatchNormalization,
    Conv1D,
    Conv2D,
    Dense,
    Dropout,
    Flatten,
    GaussianNoise,
    Input,
    MaxPool2D,
)
from keras.models import Model
from keras.utils import to_categorical
from sklearn.model_selection import train_test_split
from sklearn.utils import class_weight

from acconeer.exptool import configs

import layer_definitions


try:
    import pyqtgraph as pg
    from PyQt5 import QtCore
    PYQT_PLOTTING_AVAILABLE = True
except ImportError:
    PYQT_PLOTTING_AVAILABLE = False


class MachineLearning():
    def __init__(self, model_dimension=2):
        self.labels_dict = None
        self.model = None
        self.training_data = {"loaded": False}
        self.test_data = {"loaded": False}

        self.model_data = {
            "loaded": False,
            "y_labels": None,
            "label_list": None,
            "feature_list": None,
            "sensor_config": None,
            "frame_settings": None,
            "model_input": None,
            "model_output": None,
            "nr_of_training_maps": None,
            "layer_list": None,
            "model_dimensions": None,
        }

        self.model_dimensions = {
            "dimensionality": model_dimension,
            "input": None,
            "output": None,
            "init_shape": None,
        }

    def set_model_dimensionality(self, dim):
        if isinstance(dim, int):
            if dim > 0 and dim < 3:
                self.model_dimensions["dimensionality"] = dim
        else:
            print("Incorrect dimension input ", dim)

    def init_default_model_1D(self):
        inputs = Input(shape=self.model_dimensions["init_shape"])

        use_cnn = True
        if use_cnn:
            x = Conv1D(filters=32, kernel_size=12, activation="relu", padding="same")(inputs)
            x = Conv1D(filters=32, kernel_size=8, activation="relu", padding="same")(x)
            x = Conv1D(filters=32, kernel_size=4, activation="relu", padding="same")(x)
            x = Dropout(rate=0.25)(x)
            x = Conv1D(filters=32, kernel_size=2, activation="relu", padding="same")(x)
            x = Flatten()(x)
        else:
            x = Dense(64, activation=None)(inputs)
        x = GaussianNoise(0.1)(x)
        x = Activation(activation="relu")(x)
        x = Dense(64, activation="relu")(x)
        x = Dropout(rate=0.25)(x)
        x = Dense(64, activation="relu")(x)
        x = Dense(64, activation="relu")(x)

        predictions = Dense(self.label_num, activation="softmax")(x)

        self.model = Model(inputs=inputs, outputs=predictions)

        self.set_optimizer("adam")

    def init_default_model_2D(self):
        input_dimensions = self.model_dimensions["init_shape"]
        self.y_dim = input_dimensions[0]
        self.x_dim = input_dimensions[1]
        inputs = Input(shape=input_dimensions)

        max_kernel = min(self.y_dim, self.x_dim)
        k = min(2, max_kernel)

        x = Conv2D(filters=32, kernel_size=(k, k), padding="same", activation="relu")(inputs)
        x = self.maxpool(x)
        x = GaussianNoise(0.3)(x)
        x = Dropout(rate=0.1)(x)
        x = Conv2D(filters=64, kernel_size=(2, 2), activation="relu")(x)
        x = self.maxpool(x)
        x = Conv2D(filters=128, kernel_size=(2, 2), activation="relu")(x)
        x = self.maxpool(x)
        x = Conv2D(filters=128, kernel_size=(2, 2), activation="relu")(x)
        x = BatchNormalization()(x)
        x = self.maxpool(x)
        x = Flatten()(x)
        x = Dropout(rate=0.5)(x)
        predictions = Dense(self.label_num, activation="softmax")(x)

        self.model = Model(inputs=inputs, outputs=predictions)

        self.set_optimizer("Adam")

    def maxpool(self, x):
        x_pool = y_pool = 2
        if self.y_dim <= 15 or self.x_dim <= 15:
            y_pool = 1
            x_pool = 1

        self.x_dim /= x_pool
        self.y_dim /= y_pool

        return MaxPool2D(pool_size=(y_pool, x_pool))(x)

    def init_model(self):
        model_dim = self.model_dimensions["dimensionality"]
        input_dimensions = self.model_dimensions["init_shape"]

        if model_dim == 1:
            print("\nInitiating 1D model with {:d} inputs"
                  " and {:d} outputs".format(input_dimensions[0], self.label_num))
        elif model_dim == 2:
            print("\nInitiating 2d model with {:d}x{:d} inputs"
                  " and {:d} outputs".format(*input_dimensions, self.label_num))

        layer_list = self.model_data.get("layer_list", None)
        if layer_list is None:
            if model_dim == 1:
                self.init_default_model_1D()
            elif model_dim == 2:
                self.init_default_model_2D()
            return {"loaded": True, "model_message": ""}

        inputs = Input(shape=input_dimensions)
        nr_layers = len(layer_list)
        layer_callbacks = layer_definitions.get_layers()

        print("Building model with {} layers...".format(nr_layers))

        x = None
        nr_layers = len(layer_list)
        for idx, layer in enumerate(layer_list):
            try:
                cb = layer_callbacks[layer['name']]['class']
            except KeyError:
                print("Layer {} not found in layer_definitions.py!".format(layer['name']))

            try:
                options = {}
                if layer["params"] is not None:
                    for entry in layer["params"]:
                        opt = layer["params"][entry]
                        if isinstance(opt, list):
                            options[entry] = tuple(opt)
                        else:
                            options[entry] = opt
                print("{}: Adding {} with\n{}".format(idx + 1, layer['name'], options))
                if idx == 0 and nr_layers > 1:
                    x = cb(**options)(inputs)
                elif idx > 0 and idx < nr_layers - 1:
                    x = cb(**options)(x)
                else:
                    options.pop("units", None)
                    predictions = cb(self.label_num, **options)(x)
            except Exception as e:
                return {
                    "loaded": False,
                    "model_message": "\nLayer nr. {} failed."
                                     " Error adding {}\n{}".format(idx + 1, layer['name'], e)
                }

        self.model = Model(inputs=inputs, outputs=predictions)

        self.set_optimizer("Adam")

        return {"loaded": True, "model_message": ""}

    def set_optimizer(self, optimizer, loss="categorical_crossentropy"):
        if optimizer.lower() == "adam":
            opt_handle = Opt.Adam()
        elif optimizer.lower() == "adagrad":
            opt_handle = Opt.Adagrad()
        elif optimizer.lower() == "adadelta":
            opt_handle = Opt.Adadelta()
        elif optimizer.lower() == "rmsprop":
            opt_handle = Opt.RMSprop()
        else:
            print("Unknown optimizer {}. Using Adam!".format(optimizer))
            opt_handle = Opt.Adam()

        print("Setting model optimizer to {}".format(optimizer))
        self.model.compile(
            loss="categorical_crossentropy",
            optimizer=opt_handle,
            metrics=["accuracy"],
        )

    def train(self, train_params):
        if self.training_data["loaded"]:
            try:
                x = self.training_data["x_data"]
                y = self.model_data["y_labels"]
                epochs = train_params["epochs"]
                batch_size = train_params["batch_size"]
            except Exception as e:
                print("Incorrect training parameters! ", e)
                return False
        else:
            print("Training data not loaded!")
            return False

        model = self.model
        run_threaded = False
        if train_params.get("threaded"):
            model = train_params["model"].model
            run_threaded = True

        if "eval_data" in train_params:
            eval_data = train_params["eval_data"]
            if isinstance(eval_data, float):
                x, xTest, y, yTest = train_test_split(x, y, test_size=eval_data)
                eval_data = (xTest, yTest)
        else:
            eval_data = None

        y_ints = [d.argmax() for d in y]
        class_weights = class_weight.compute_class_weight('balanced', np.unique(y_ints), y_ints)
        class_weights = dict(enumerate(class_weights))

        cb = []
        if "plot_cb" in train_params:
            plot_cb = train_params["plot_cb"]
            stop_cb = None
            save_best = None
            if "stop_cb" in train_params:
                stop_cb = train_params["stop_cb"]
            if "save_best" in train_params:
                save_best = train_params["save_best"]
            steps = int(np.ceil(x.shape[0] / batch_size))
            func = TrainCallback(plot_cb=plot_cb,
                                 steps_per_epoch=steps,
                                 stop_cb=stop_cb,
                                 save_best=save_best,
                                 parent=self)
            cb.append(func)
            verbose = 0
        else:
            verbose = 1

        if "dropout" in train_params:
            dropout = train_params["dropout"]
            if isinstance(dropout, dict):
                if dropout["monitor"] in ["acc", "val_acc", "loss", "val_loss"]:
                    cb_early_stop = EarlyStopping(monitor=dropout["monitor"],
                                                  min_delta=dropout["min_delta"],
                                                  patience=dropout["patience"],
                                                  verbose=0,
                                                  mode="auto"
                                                  )
                cb.append(cb_early_stop)

        # This will only save the model, nothing else!
        '''
        if train_params.get("save_best"):
            cb_best = ModelCheckpoint(os.path.join(train_params["save_best"], "best_model.npy"),
                                      monitor="val_loss",
                                      verbose=0,
                                      save_best_only=True,
                                      save_weights_only=False,
                                      mode="auto",
                                      period=1
                                      )
            cb.append(cb_best)
        '''

        if run_threaded:
            tf_session = train_params["session"].as_default()
            tf_graph = train_params["graph"].as_default()
        else:
            tf_session = self.tf_session.as_default()
            tf_graph = self.tf_graph.as_default()

        optimizer = None
        if train_params.get("optimizer"):
            optimizer = train_params["optimizer"]

        with tf_session:
            with tf_graph:
                if optimizer is not None:
                    self.set_optimizer(optimizer)
                if "learning_rate" in train_params:
                    K.set_value(model.optimizer.lr, train_params["learning_rate"])
                history = model.fit(x,
                                    y,
                                    epochs=epochs,
                                    batch_size=batch_size,
                                    callbacks=cb,
                                    validation_data=eval_data,
                                    verbose=verbose,
                                    class_weight=class_weights,
                                    )

        if run_threaded:
            return model, self.get_current_graph(), self.get_current_session()
        else:
            return history

    def set_learning_rate(self, rate):
        K.set_value(self.model.optimizer.lr, rate)

    def eval(self, x, y):
        with self.tf_session.as_default():
            with self.tf_graph.as_default():
                test_loss, test_acc = self.model.evaluate(x, y)
                print("\nTest result:")
                print("Loss: ", test_loss, "Accuracy: ", test_acc)

    def predict(self, x="internal"):
        if x == "internal" and self.training_data["loaded"]:
            # Predict training data
            x = self.training_data["x_data"]

        if len(x.shape) == len(self.model.input_shape) - 1:
            if x.shape[0] == self.model.input_shape[1]:
                x = np.expand_dims(x, 0)
            else:
                x = np.expand_dims(x, len(x.shape))
        if len(x.shape) == len(self.model.input_shape) - 2:
            x = np.expand_dims(x, 0)
            x = np.expand_dims(x, len(x.shape))

        if len(x.shape) != len(self.model.input_shape):
            print("Wrong data shapes:\n Model: {}\n Test: {}\n".format(self.model.input_shape,
                                                                       x.shape,))
            pass
            return None

        with self.tf_graph.as_default():
            with self.tf_session.as_default():
                prediction = self.model.predict(x)
        result = list()

        num2label = {}
        for key in self.labels_dict:
            num2label[self.labels_dict[key]] = key

        for pred in prediction:
            confidence = 0
            prediction_label = ""
            res = {}
            category = {}
            for p in range(len(pred)):
                label = num2label[p]
                if pred[p] > confidence:
                    prediction_label = label
                    confidence = pred[p]
                category[label] = [pred[p], p]
            res["label_predictions"] = category
            res["number_labels"] = len(pred)
            res["prediction"] = prediction_label
            res["confidence"] = confidence
            res["label_num"] = np.argmax(pred)
            result.append(res)
        return result

    def label_conversion(self, labels):
        label_num = 0
        converted_labels = np.zeros(len(labels))
        labels_dict = {}
        for i, label in enumerate(labels):
            try:
                labels_dict[label]
            except Exception:
                labels_dict[label] = label_num
                label_num += 1
            converted_labels[i] = labels_dict[label]
        return converted_labels, label_num, labels_dict

    def label_assignment(self, labels, labels_dict):
        assigned_labels = np.zeros(len(labels))
        for i, label in enumerate(labels):
            assigned_labels[i] = labels_dict[label]
        return assigned_labels

    def labelnum2text(self, num, label_dict):
        for key in label_dict:
            if label_dict[key] == num:
                return key
        return None

    def load_train_data(self, files, layer_list=None, model_exists=False, load_test_data=False):
        err_tip = "\nTry clearing training before loading more data!"
        data = []
        stored_configs = []
        feature_lists = []
        frame_settings_list = []
        feature_map_dims = []
        files_loaded = 0
        files_failed = []
        info = {
            "success": False,
            "message": "",
            "model_initialized": False,
        }
        for file in files:
            try:
                file_data = np.load(file, allow_pickle=True).item()
                conf = configs.load(file_data["sensor_config"])
                stored_configs.append(conf)
                feature_lists.append(file_data["feature_list"])
                frame_settings_list.append(file_data["frame_settings"])
                feature_map_dims.append(
                    file_data["frame_data"]["ml_frame_data"]["frame_list"][0]["feature_map"].shape
                )
                data.append(file_data)
            except Exception:
                print("File error in:\n", file)
                traceback.print_exc()
                files_failed.append(file)
            else:
                files_loaded += 1

        if not files_loaded:
            info["message"] = "No valid files found"
            return {"info": info}

        data_type = "training"
        if load_test_data:
            if self.labels_dict is None:
                message = "Load train data first"
                return {"info": info}
            data_type = "test"

        if data_type == "training":
            if model_exists:
                self.model_dimensions["input"] = self.model.input_shape[1:-1]
                self.model_dimensions["output"] = self.model.output_shape[-1]
            else:
                self.model_dimensions["dimensionality"] = 2
                self.model_dimensions["input"] = feature_map_dims[0]
                if feature_map_dims[0][1] == 1:
                    self.model_dimensions["dimensionality"] = 1
        else:
            if not self.training_data["loaded"]:
                info["message"] = "Load training data first!"
                return {"info": info}

        for i in range(1, files_loaded):
            # TODO: Check that files are compatible
            map_dims = self.model_dimensions["input"]
            if map_dims != feature_map_dims[i]:
                message = "Input dimenions not matching:\nModel {} - Data {}".format(
                    map_dims,
                    feature_map_dims[i])
                message += err_tip
                info["message"] = message
                return {"info": info}

        raw_labels = []
        feature_maps = []
        for d in data:
            fdata = d["frame_data"]["ml_frame_data"]["frame_list"]
            for data_idx in fdata:
                feature_maps.append(data_idx["feature_map"])
                raw_labels.append(data_idx["label"])

        feature_map_data = np.stack(feature_maps)
        if self.model_dimensions["dimensionality"] == 2:
            feature_map_data = np.expand_dims(
                feature_map_data,
                self.model_dimensions["dimensionality"] + 1)
        self.model_dimensions["nr_of_training_maps"] = feature_map_data.shape[0]

        if data_type == "training":
            if not model_exists or not self.label_num:
                data_labels, self.label_num, self.labels_dict = self.label_conversion(raw_labels)
                self.model_dimensions["output"] = self.label_num
            else:
                data_labels = self.label_assignment(raw_labels, self.labels_dict)
                output = self.model_dimensions["output"]
                if self.label_num != output:
                    message = "Output dimensions not matching:\nModel {} - Data {}".format(
                        output,
                        self.label_num)
                    info["message"] = message + err_tip
                    return {"info": info}
        else:
            data_labels = self.label_assignment(raw_labels, self.labels_dict)

        label_categories = to_categorical(data_labels, self.label_num)

        if data_type == "training":
            self.model_dimensions["init_shape"] = feature_map_data.shape[1:]
            if not model_exists:
                self.model_data["layer_list"] = layer_list
                model_status = self.clear_model(reinit=True)
            else:
                model_status = {"loaded": True, "model_message": ""}

        message = "Loaded {} data with shape {}\n".format(data_type, feature_map_data.shape)
        message += "Found labels:\n"
        for label in self.labels_dict:
            message += label + "\n"

        if files_failed:
            message += "Failed to load some files:\n"
            for f in files_failed:
                message += f + "\n"

        loaded_data = self.training_data
        if data_type == "training":
            self.training_data = {
                "loaded": True,
                "x_data": feature_map_data,
                "raw_labels": raw_labels,
            }
            model_data = {
                "loaded": model_status["loaded"],
                "y_labels": label_categories,
                "label_list": self.get_label_list(),
                "feature_list": feature_lists[0],
                "frame_settings": frame_settings_list[0],
                "sensor_config": stored_configs[0],
                "model_dimensions": self.model_dimensions,
                "layer_list": layer_list,
                "model_input": self.model_dimensions["input"],
                "model_output": self.model_dimensions["output"],
                "nr_of_training_maps": self.model_dimensions["nr_of_training_maps"],
            }
            for key in model_data:
                self.model_data[key] = model_data[key]
        else:
            self.test_data = {
                "loaded": True,
                "test_data": feature_map_data,
                "raw_labels": raw_labels,
            }
            loaded_data = self.test_data

        info = {
            "success": True,
            "message": message,
            "model_initialized": model_status["loaded"],
            "model_status": model_status["model_message"],
        }

        if model_status["loaded"] is True:
            counted = self.count_variables()
            self.model_data["trainable"] = counted["trainable"]
            self.model_data["non_trainable"] = counted["non_trainable"]
            self.model_data["keras_layer_info"] = self.model.layers
            self.model_data["layer_list"] = layer_list
        else:
            if not isinstance(model_status, str):
                info["model_status"] = "Model not initialized"

        return {"info": info, "model_data": self.model_data, "loaded_data": loaded_data}

    def load_test_data(self, files):
        return self.load_train_data(files, load_test_data=True)

    def save_model(self, file, feature_list, sensor_config, frame_settings):
        try:
            info = {
                "labels_dict": self.labels_dict,
                "model_dimensions": self.model_dimensions,
                "feature_list": feature_list,
                "sensor_config": sensor_config._dumps(),
                "model": self.model,
                "frame_settings": frame_settings,
                "nr_of_training_maps": self.model_dimensions["nr_of_training_maps"],
            }
            np.save(file, info)
        except Exception as e:
            message = "Error saving model:\n{}".format(e)
        else:
            message = None

        return message

    def get_model_data(self):
        return self.model_data

    def load_model(self, file):
        try:
            del self.model
            self.model_data["loaded"] = False
            info = np.load(file, allow_pickle=True)
            self.model = info.item()["model"]
            self.labels_dict = info.item()["labels_dict"]
            self.model_dimensions = info.item()["model_dimensions"]
            self.label_num = self.model_dimensions["output"]
            feature_list = info.item()["feature_list"]
            sensor_config = configs.load(info.item()["sensor_config"])
            frame_settings = info.item()["frame_settings"]
            self.tf_session = K.get_session()
            self.tf_graph = tf.get_default_graph()
            with self.tf_session.as_default():
                with self.tf_graph.as_default():
                    self.model._make_predict_function()
        except Exception as e:
            error_text = self.error_to_text(e)
            message = "Error in load model:\n{}".format(error_text)
            return {
                "loaded": False,
                "message": message,
            }
        else:
            gui_layer_conf = layer_definitions.get_layers()
            layer_list = []
            for l in self.model.layers:
                l_conf = l.get_config()
                l_name = l_conf["name"].rsplit("_", 1)[0]
                if l_name in gui_layer_conf:
                    g_conf = gui_layer_conf[l_name]["params"]
                    layer = {
                        "name": l_name,
                        "class": gui_layer_conf[l_name]["class_str"],
                        "params": {},
                    }
                    if g_conf is None:
                        layer["params"] = None
                    else:
                        for p in l_conf:
                            if p in g_conf:
                                if isinstance(l_conf[p], tuple):
                                    layer["params"][p] = list(l_conf[p])
                                else:
                                    layer["params"][p] = l_conf[p]
                    layer_list.append(layer)
                else:
                    if l_name != "input":
                        print("Keras layer {} not found in layer_definitions.py!".format(l_name))

        counted = self.count_variables()

        labels = self.get_label_list()
        label_categories = None
        if self.training_data["loaded"]:
            try:
                data_labels = self.label_assignment(
                    self.training_data["raw_labels"],
                    self.labels_dict
                )
                label_categories = to_categorical(data_labels, self.label_num)
            except Exception as e:
                print("Loaded data incompatible with model data!\n", e)
                self.trainning = {"loaded": False}
                label_categories = None

        message = "Loaded model with:\n"\
                  "input shape    :{}\n"\
                  "output shape   :{}\n"\
                  "nr of features :{}\n"\
                  "labels         :{}\n"\
                  "Trained with {} features".format(
                      self.model_dimensions["input"],
                      self.model_dimensions["output"],
                      len(feature_list),
                      labels,
                      self.model_dimensions.get("nr_of_training_maps", "N/A")
                  )

        self.model_data = {
            "loaded": True,
            "message": message,
            "y_labels": label_categories,
            "label_list": labels,
            "feature_list": feature_list,
            "sensor_config": sensor_config,
            "frame_settings": frame_settings,
            "layer_list": layer_list,               # GUI format layer list
            "keras_layer_info": self.model.layers,  # Keras format layer list
            "trainable": counted["trainable"],
            "non_trainable": counted["non_trainable"],
            "model_input": self.model_dimensions["input"],
            "model_output": self.model_dimensions["output"],
            "model_dimensions": self.model_dimensions,
        }
        try:
            self.model_data["nr_of_training_maps"] = self.model_dimensions["nr_of_training_maps"]
        except KeyError:
            self.model_data["nr_of_training_maps"] = 0

        return self.model_data

    def clear_model(self, reinit=False):
        if self.model is not None:
            K.clear_session()
            del self.model
            self.model = None
            self.model_data["loaded"] = False

        if reinit and self.model_dimensions is not None:
            self.tf_session = K.get_session()
            self.tf_graph = tf.get_default_graph()
            with self.tf_session.as_default():
                with self.tf_graph.as_default():
                    status = self.init_model()
                    if not status["loaded"]:
                        self.clear_model()
                    else:
                        self.model_data["loaded"] = True
                    return status
        else:
            return {"loaded": False, "model_message": "Nothing to reinitialize!"}

    def update_model_layers(self, layer_list):
        self.model_data["layer_list"] = layer_list
        model_status = self.clear_model(reinit=True)

        info = {
            "model_initialized": model_status["loaded"],
            "model_message": model_status["model_message"],
        }

        if model_status["loaded"]:
            self.model_data["keras_layer_info"] = self.model.layers

        return {"info": info, "model_data": self.model_data}

    def count_variables(self):
        if self.model is not None:
            trainable = int(
                np.sum([K.count_params(p) for p in set(self.model.trainable_weights)]))
            non_trainable = int(
                np.sum([K.count_params(p) for p in set(self.model.non_trainable_weights)]))
        else:
            return None

        return ({"trainable": trainable, "non_trainable": non_trainable})

    def get_current_session(self, graph=None):
        return self.tf_session

    def get_current_graph(self):
        return self.tf_graph

    def set_current_session(self, session):
        K.set_session(session)

    def clear_training_data(self):
        self.model_data["y_labels"] = None
        self.training_data = {"loaded": False}
        self.test_data = {"loaded": False}

    def get_labels(self):
        return self.labels_dict

    def get_label_list(self):
        label_list = list()
        for i in range(len(self.labels_dict)):
            for key in self.labels_dict:
                if self.labels_dict[key] == i:
                    label_list.append(key)
        return label_list

    def confusion_matrix(self, y_test, predictions, print_to_cmd=False):
        matrix = np.zeros((self.label_num, self.label_num), dtype=int)
        for idx, p in enumerate(predictions):
            matrix[int(np.argmax(y_test[idx])), int(p["label_num"])] += 1
        row_labels = []
        max_len = 0
        for i in range(matrix.shape[0]):
            for key in self.labels_dict:
                if self.labels_dict[key] == i:
                    row_labels.append(key)
                    if len(key) > max_len:
                        max_len = len(key)

        if print_to_cmd:
            print("")
            for row_label, row in zip(row_labels, matrix):
                print("%s [%s]" % (row_label.ljust(max_len),
                                   " ".join("%09s" % i for i in row)))
            print("%s %s" % ("".ljust(max_len),
                             " ".join("%s" % i.ljust(11) for i in row_labels)))

        return {"matrix": matrix, "labels": row_labels}

    def error_to_text(self, error):
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        err_text = "File: {}\nLine: {}\nError: {}".format(fname, exc_tb.tb_lineno, error)

        return err_text


class TrainCallback(Callback):
    def __init__(self, plot_cb=None, steps_per_epoch=None, stop_cb=None, save_best=None,
                 parent=None):
        self.parent = parent
        self.plot = plot_cb
        self.stop_cb = stop_cb
        self.steps_per_epoch = steps_per_epoch
        self.epoch = 0
        self.batch = 0
        self.save_best = save_best
        self.val_loss = np.inf

    def on_batch_end(self, batch, logs=None):
        self.batch += 1
        self.send_data(logs)

    def on_epoch_end(self, epoch, logs=None):
        self.epoch += 1
        self.send_data(logs)

        if self.save_best:
            try:
                if logs["val_loss"] < self.val_loss:
                    self.val_loss = logs["val_loss"]
                    fname = "model_epoch_{}_val_loss_{:.04f}".format(self.epoch, self.val_loss)
                    fname = os.path.join(self.save_best["folder"], fname)
                    self.parent.save_model(fname,
                                           self.save_best["feature_list"],
                                           self.save_best["sensor_config"],
                                           self.save_best["frame_settings"],
                                           )
            except Exception as e:
                print(e)

    def send_data(self, data):
        if "steps_per_epoch" not in data:
            data["steps_per_epoch"] = self.steps_per_epoch

        if self.plot is not None:
            self.plot(data)

        if self.stop_cb is not None:
            try:
                stop_training = self.stop_cb()
                if stop_training:
                    self.stopped_epoch = self.epoch
                    self.model.stop_training = True
            except Exception as e:
                print("Failed to call stop callback! ", e)
                pass


class KerasPlotting:
    def __init__(self, epoch_history=20):

        if not PYQT_PLOTTING_AVAILABLE:
            print("Warning: Plotting functionality not available.")

        self.epoch_history = epoch_history
        self.first = True
        self.history = {
            "acc": [],
            "loss": [],
            "val_acc": [],
            "val_loss": [],
            "train_x": [],
            "val_x": [],
            "epoch_idx": [],
        }
        self.current_epoch = 0
        self.tendency_plots = False

    def setup(self, win):
        win.setWindowTitle("Keras training results")

        self.acc_plot_window = win.addPlot(row=0, col=0, title="Accuracy results")
        self.acc_plot_window.showGrid(x=True, y=True)
        self.acc_plot_window.addLegend(offset=(-10, 10))
        self.acc_plot_window.setYRange(0, 1)
        self.acc_plot_window.setXRange(0, 1)
        self.acc_plot_window.setLabel("left", "Accuracy")
        self.acc_plot_window.setLabel("bottom", "Epoch")

        self.progress_acc = pg.TextItem(color="k", anchor=(0, 1), fill="#f0f0f0")
        self.progress_acc.setPos(0, 0)
        self.progress_acc.setZValue(2)
        self.acc_plot_window.addItem(self.progress_acc, ignoreBounds=True)

        self.loss_plot_window = win.addPlot(row=1, col=0, title="Loss results")
        self.loss_plot_window.showGrid(x=True, y=True)
        self.loss_plot_window.addLegend(offset=(-10, 10))
        self.loss_plot_window.setYRange(0, 1)
        self.loss_plot_window.setXRange(0, 1)
        self.loss_plot_window.setLabel("left", "Loss")
        self.loss_plot_window.setLabel("bottom", "Epoch")

        self.progress_loss = pg.TextItem(color="k", anchor=(0, 1), fill="#f0f0f0")
        self.progress_loss.setPos(.5, 0.5)
        self.progress_loss.setZValue(2)
        self.loss_plot_window.addItem(self.progress_loss, ignoreBounds=True)

        hp = self.history_plots = {}
        pen = pg.mkPen("#ff7f0e", width=2)
        hp["acc"] = self.acc_plot_window.plot(pen=pen, name="Accuracy")
        hp["loss"] = self.loss_plot_window.plot(pen=pen, name="Loss")
        pen = pg.mkPen("#2ca02c", width=2)
        hp["val_acc"] = self.acc_plot_window.plot(pen=pen, name="Val. Accuracy")
        hp["val_loss"] = self.loss_plot_window.plot(pen=pen, name="Val. Loss")
        if self.tendency_plots:
            pen = pg.mkPen("#0000ff", width=2, style=QtCore.Qt.DotLine)
            hp["acc_tendency"] = self.acc_plot_window.plot(pen=pen, name="Tendency")
            hp["loss_tendency"] = self.loss_plot_window.plot(pen=pen, name="Tendency")

    def process(self, data=None, flush_data=False):
        if flush_data:
            for key in self.history:
                self.history[key] = []
            for key in self.history_plots:
                self.history_plots[key].setData([], [])
            self.history["epoch_idx"].append(0)
            self.history["val_x"].append(0)
            self.progress_acc.setText("")
            self.progress_loss.setText("")
            self.current_epoch = 0

        self.update(data)

    def update(self, data):
        if data is None:
            return

        if not isinstance(data, dict):
            print("Train log data has wrong type: ", type(data))
            return
        if "loss" not in data or "acc" not in data:
            print("Cannot process training logs... ")
            return

        hp = self.history_plots
        h = self.history

        if "val_loss" in data:
            self.current_epoch += 1
            h["val_x"].append(self.current_epoch)
            h["epoch_idx"].append(len(h["train_x"]) + 1)
        epoch = self.current_epoch

        batch = 0
        if "batch" in data:
            batch = data["batch"] + 1

        if len(h["acc"]) == 1:
            h["val_acc"].append(h["acc"][0])
            h["val_loss"].append(h["loss"][0])

        increment = 1
        if "steps_per_epoch" in data:
            spe = data["steps_per_epoch"]
            increment = 1 / (spe + 1)
            if len(h["train_x"]):
                increment += h["train_x"][-1]
        h["train_x"].append(increment)

        hist_key_list = ["acc", "accuracy", "val_acc", "val_accuracy", "loss", "val_loss"]

        for data_key in data:
            for hist_key in hist_key_list:
                if hist_key == data_key:
                    h[hist_key].append(data[data_key])
                    x = h["train_x"]
                    if "val" in data_key:
                        x = h["val_x"]
                    hp[hist_key].setData(x, h[hist_key])

        self.acc_plot_window.setXRange(max(0, epoch - self.epoch_history), epoch + 2)
        self.loss_plot_window.setXRange(max(0, epoch - self.epoch_history), epoch + 2)

        if len(h["val_acc"]):
            train_idx = h["epoch_idx"][max(0, epoch - self.epoch_history)]
            val_idx = max(0, epoch - self.epoch_history)
            max_acc = max(max(h["val_acc"][val_idx:]), max(h["acc"][train_idx:]))
            min_acc = min(min(h["val_acc"][val_idx:]), min(h["acc"][train_idx:]))

            max_loss = max(max(h["val_loss"][val_idx:]), max(h["loss"][train_idx:]))
            min_loss = min(min(h["val_loss"][val_idx:]), min(h["loss"][train_idx:]))

            self.acc_plot_window.setYRange(max(0.9 * min_acc, 0), 1.1 * max_acc)
            self.loss_plot_window.setYRange(max(0.9 * min_loss, 0), 1.1 * max_loss)
            self.progress_acc.setPos(max(0, epoch - self.epoch_history), max(0.9 * min_acc, 0))
            self.progress_loss.setPos(max(0, epoch - self.epoch_history), max(0.9 * max_loss, 0))

            if self.tendency_plots:
                acc_z = np.polyfit(h["val_x"][val_idx:], h["val_acc"][val_idx:], 1)
                acc_p = np.poly1d(acc_z)
                hp["acc_tendency"].setData(h["val_x"][val_idx:], acc_p(h["val_x"][val_idx:]))
                loss_z = np.polyfit(h["val_x"][val_idx:], h["val_loss"][val_idx:], 1)
                loss_p = np.poly1d(loss_z)
                hp["loss_tendency"].setData(h["val_x"][val_idx:], loss_p(h["val_x"][val_idx:]))

        p_acc = "Epoch: {} -> Batch {} of {}\n".format(epoch, batch, spe)
        p_acc += "Acc: {:1.2E} ".format(h["acc"][-1])
        if len(h["val_acc"]):
            p_acc += "Val-Acc: {:1.2E}".format(h["val_acc"][-1])

        p_loss = "Loss: {:1.2E} ".format(h["loss"][-1])
        if len(h["val_loss"]):
            p_loss += "Val-Loss: {:1.2E}".format(h["val_loss"][-1])

        self.progress_acc.setText(p_acc)
        self.progress_loss.setText(p_loss)
