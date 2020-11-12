import os
import sys
import traceback

import numpy as np

from acconeer.exptool import configs

import ml_helper


try:
    import pyqtgraph as pg

    from PyQt5 import QtCore

    PYQT_PLOTTING_AVAILABLE = True
except ImportError:
    PYQT_PLOTTING_AVAILABLE = False

import tensorflow as tf


tf_version = tf.__version__.split(".")[0]
print("Tensorflow version {} detected".format(tf.__version__))
if tf.__version__.split(".")[0] == "1":
    import gui.ml.keras_processing_tf1 as kp_tf
elif tf.__version__.split(".")[0] == "2":
    import gui.ml.keras_processing_tf2 as kp_tf
else:
    print("Unsupported TensorFlow version...")
    raise ImportError


class MachineLearning(kp_tf.ACC_ML):
    def __init__(self):
        self.labels_dict = None
        self.model = None
        self.training_data = {"loaded": False}
        self.test_data = {"loaded": False}
        self.label_num = 0

        model_data = {
            "loaded": False,
            "y_labels": None,
            "label_list": None,
            "feature_list": None,
            "sensor_config": None,
            "frame_settings": None,
            "nr_of_training_maps": None,
            "layer_list": None,
            "feature_dimension": None,
            "time_distributed": 1,
            "input": None,
            "output": None,
            "keras_layer_info": None,
            "trainable": None,
            "non_trainable": None,
            "tf_version": tf_version,
        }

        self.model_data = ObjectDict(model_data)

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
        files_loaded = []
        files_failed = []
        model_exists = self.model_data.loaded
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
                files_loaded.append(file)

        if not len(files_loaded):
            info["message"] = "No valid files found"
            return {"info": info}

        data_type = "training"
        if load_test_data:
            if self.labels_dict is None:
                message = "Load train data first"
                return {"info": info}
            data_type = "test"

        transpose = False
        if feature_map_dims[0][0] == 1 or feature_map_dims[0][1] == 1:
            model_dimension = 1
            if feature_map_dims[0][0] == 1:
                feature_map_dims[0] = feature_map_dims[0][::-1]
                transpose = True
        else:
            model_dimension = 2

        if data_type == "training":
            if not model_exists:
                self.model_data.feature_dimension = feature_map_dims[0]
        else:
            if not self.training_data["loaded"]:
                info["message"] = "Load training data first!"
                return {"info": info}

        for i in range(1, len(files_loaded)):
            # TODO: Check that files are compatible
            map_dims = self.model_data.feature_dimension
            current_dim = feature_map_dims[i]
            if transpose:
                current_dim = current_dim[::-1]
            if map_dims != current_dim:
                message = "Input dimenions not matching:\nModel {} - Data {}".format(
                    map_dims,
                    feature_map_dims[i])
                message += err_tip
                info["message"] = message
                print(files_loaded[i])
                return {"info": info}

        if data_type == "training":
            if not model_exists:
                if layer_list is not None:
                    self.set_model_layers(layer_list)

        raw_labels = []
        feature_maps = []
        frame_info = data[0]["frame_data"]["ml_frame_data"]["frame_info"]
        for data_index, d in enumerate(data):
            fdata = d["frame_data"]["ml_frame_data"]["frame_list"]
            if self.model_data.time_distributed:
                time_series = frame_info.get("time_series", 1)
                if self.model_data.time_distributed != time_series:
                    print("Inconsistent time series values found:")
                    print("Model: {}".format(self.model_data.time_distributed))
                    print("Data : {}".format(time_series))
                    frame_info["time_series"] = self.model_data.time_distributed
            for subdata_index, frame in enumerate(fdata):
                feature_map = frame["feature_map"]
                if self.model_data.time_distributed > 1:
                    feature_map = ml_helper.convert_time_series(feature_map, frame_info)
                if transpose:
                    feature_map = feature_map.T
                feature_maps.append(feature_map)
                raw_labels.append(frame["label"])

        feature_map_data = np.stack(feature_maps)
        if model_dimension == 2:
            feature_map_data = np.expand_dims(feature_map_data, -1)
        self.model_data.nr_of_training_maps = feature_map_data.shape[0]

        if data_type == "training":
            if not model_exists or not self.label_num:
                data_labels, self.label_num, self.labels_dict = self.label_conversion(raw_labels)
                self.model_data.output = self.label_num
            else:
                data_labels = self.label_assignment(raw_labels, self.labels_dict)
                output = self.model_data.output
                if self.label_num != output:
                    message = "Output dimensions not matching:\nModel {} - Data {}".format(
                        output,
                        self.label_num)
                    info["message"] = message + err_tip
                    return {"info": info}
        else:
            data_labels = self.label_assignment(raw_labels, self.labels_dict)

        label_categories = self.convert_to_categorical(data_labels, self.label_num)

        if data_type == "training":
            if not model_exists:
                if layer_list is not None:
                    self.set_model_layers(layer_list)
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
            self.model_data.trainable = counted["trainable"]
            self.model_data.non_trainable = counted["non_trainable"]
            self.model_data.keras_layer_info = self.model.layers
        else:
            if not isinstance(model_status, str):
                info["model_status"] = "Model not initialized"

        return {"info": info, "model_data": self.model_data, "loaded_data": loaded_data}

    def load_test_data(self, files):
        return self.load_train_data(files, load_test_data=True)

    def get_model_data(self):
        return self.model_data

    def set_model_data(self, model_data):
        for key in model_data:
            if key in self.model_data:
                self.model_data[key] = model_data[key]
            else:
                print("Unknown model parameter: {}".format(key))

    def set_model_layers(self, layer_list):
        self.model_data.time_distributed = 1
        for l in layer_list:
            if "lstm" in l["name"] and l.get("is_active", True):
                steps = l["params"].get("steps", None)
                if steps is None:
                    steps = 1
                    print("Warning: Missing time steps for LSTM")
                self.model_data.time_distributed = steps
        self.model_data.layer_list = layer_list

    def update_model_layers(self, layer_list):
        self.set_model_layers(layer_list)
        model_status = self.clear_model(reinit=True)

        info = {
            "model_initialized": model_status["loaded"],
            "model_message": model_status["model_message"],
        }

        if model_status["loaded"]:
            self.model_data.keras_layer_info = self.model.layers

        return {"info": info, "model_data": self.model_data}

    def clear_training_data(self):
        self.model_data.y_labels = None
        self.training_data = {"loaded": False}
        self.test_data = {"loaded": False}
        if not self.model_data.loaded:
            self.label_num = 0
            self.labels_dict = None

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
        err_text = "File: {}<br>Line: {}<br>Error: {}".format(fname, exc_tb.tb_lineno, error)

        return err_text


class ObjectDict(dict):
    def __getattr__(self, key):
        if key in self:
            return self[key]
        else:
            raise AttributeError("Key {} not found".format(key))

    def __setattr__(self, key, value):
        self[key] = value

    def __delattr__(self, key):
        if key in self:
            del self[key]
        else:
            raise AttributeError("Key {} not found".format(key))


class KerasPlotting:
    def __init__(self, epoch_history=20):

        if not PYQT_PLOTTING_AVAILABLE:
            print("Warning: Plotting functionality not available.")

        self.epoch_history = epoch_history
        self.first = True
        self.history = {
            "acc": [],
            "accuracy": [],
            "loss": [],
            "val_acc": [],
            "val_accuracy": [],
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

        hp = self.history_plots
        h = self.history

        if "accuracy" in data:
            acc_key = "accuracy"
        else:
            acc_key = "acc"

        if "val_loss" in data:
            self.current_epoch += 1
            h["val_x"].append(self.current_epoch)
            h["epoch_idx"].append(len(h["train_x"]) + 1)
        epoch = self.current_epoch

        batch = 0
        if "batch" in data:
            batch = data["batch"] + 1

        if len(h[acc_key]) == 1:
            h["val_acc"].append(h[acc_key][0])
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
                    if hist_key == "accuracy":
                        plot_key = "acc"
                    elif hist_key == "val_accuracy":
                        plot_key = "val_acc"
                    else:
                        plot_key = hist_key
                    min_len = min(len(x), len(h[hist_key]))
                    hp[plot_key].setData(x[0:min_len], h[hist_key][0:min_len])

        self.acc_plot_window.setXRange(max(0, epoch - self.epoch_history), epoch + 2)
        self.loss_plot_window.setXRange(max(0, epoch - self.epoch_history), epoch + 2)

        if len(h["val_acc"]):
            train_idx = h["epoch_idx"][max(0, epoch - self.epoch_history)]
            val_idx = max(0, epoch - self.epoch_history)
            max_acc = max(max(h["val_acc"][val_idx:]), max(h[acc_key][train_idx:]))
            min_acc = min(min(h["val_acc"][val_idx:]), min(h[acc_key][train_idx:]))

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
        p_acc += "Acc: {:1.2E} ".format(h[acc_key][-1])
        if len(h["val_acc"]):
            p_acc += "Val-Acc: {:1.2E}".format(h["val_acc"][-1])

        p_loss = "Loss: {:1.2E} ".format(h["loss"][-1])
        if len(h["val_loss"]):
            p_loss += "Val-Loss: {:1.2E}".format(h["val_loss"][-1])

        self.progress_acc.setText(p_acc)
        self.progress_loss.setText(p_loss)
