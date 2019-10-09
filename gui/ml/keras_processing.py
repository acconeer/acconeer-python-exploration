from keras.models import Model
from keras import backend as K
from keras.layers import (Dense, Dropout, Input, GaussianNoise, Activation, Conv1D, Conv2D,
                          MaxPool2D, Flatten, BatchNormalization)
from keras.utils import to_categorical
from keras.callbacks import EarlyStopping, ModelCheckpoint, Callback
from sklearn.model_selection import train_test_split

import numpy as np
import argparse

from acconeer_utils import example_utils
import pyqtgraph as pg
from helper import ErrorFormater
import tensorflow as tf


class MachineLearning():
    def __init__(self, model_dimension=2):
        self.labels_dict = None
        self.model = None
        self.model_dimensions = {
            "dimensionality": model_dimension,
            "input": None,
            "output": None,
            "init_shape":  None,
        }
        self.format_error = ErrorFormater()
        self.model_params = None

    def set_model_dimensionality(self, dim):
        if isinstance(dim, int):
            if dim > 0 and dim < 3:
                self.model_dimensions["dimensionality"] = dim
        else:
            print("Incorrect dimension input ", dim)

    def init_model_1D(self, input_dimensions):
        print("\nInitiating 1D model with {:d} inputs and {:d} outputs".format(input_dimensions[0],
                                                                               self.label_num))

        inputs = Input(shape=input_dimensions)

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

        self.model.compile(
            loss="categorical_crossentropy",
            optimizer="adam",
            metrics=["accuracy"]
        )

    def init_model_2D(self, input_dimensions):
        self.y_dim = input_dimensions[0]
        self.x_dim = input_dimensions[1]
        print("\nInitiating 2d model with {:d}x{:d} inputs"
              " and {:d} outputs".format(self.y_dim, self.x_dim,
                                         self.label_num))
        inputs = Input(shape=input_dimensions)

        max_kernel = min(self.y_dim, self.x_dim)
        k = min(3, max_kernel)

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
        self.model.summary()

        self.model.compile(
            loss="categorical_crossentropy",
            optimizer="adam",
            metrics=["accuracy"]
        )

    def maxpool(self, x):
        x_pool = y_pool = 2
        if self.y_dim <= 9 or self.x_dim <= 9:
            y_pool = 1
            x_pool = 1

        self.x_dim /= x_pool
        self.y_dim /= y_pool

        return MaxPool2D(pool_size=(y_pool, x_pool))(x)

    def train(self, train_params):
        try:
            x = train_params["x"]
            y = train_params["y"]
            epochs = train_params["epochs"]
            batch_size = train_params["batch_size"]
        except Exception as e:
            print("Incorrect training parameters! ", e)

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

        cb = []
        if "plot_cb" in train_params:
            plot_cb = train_params["plot_cb"]
            stop_cb = None
            if "stop_cb" in train_params:
                stop_cb = train_params["stop_cb"]
            steps = int(np.ceil(x.shape[0] / batch_size))
            func = TrainCallback(plot_cb=plot_cb, steps_per_epoch=steps, stop_cb=stop_cb)
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

        if train_params.get("save_best"):
            cb_best = ModelCheckpoint(train_params["save_best"],
                                      monitor="val_acc",
                                      verbose=0,
                                      save_best_only=True,
                                      save_weights_only=False,
                                      mode="auto",
                                      period=1
                                      )
            cb.append(cb_best)

        if run_threaded:
            tf_session = train_params["session"].as_default()
            tf_graph = train_params["graph"].as_default()
        else:
            tf_session = self.tf_session.as_default()
            tf_graph = self.tf_graph.as_default()

        with tf_session:
            with tf_graph:
                if "learning_rate" in train_params:
                    K.set_value(model.optimizer.lr, train_params["learning_rate"])
                history = model.fit(x,
                                    y,
                                    epochs=epochs,
                                    batch_size=batch_size,
                                    callbacks=cb,
                                    validation_data=eval_data,
                                    verbose=verbose
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

    def predict(self, x):
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
            return None

        with self.tf_graph.as_default():
            with self.tf_session.as_default():
                prediction = self.model.predict(x)

        result = list()
        for pred in prediction:
            res = {}
            category = {}
            for p in range(len(pred)):
                category[self.labelnum2text(p, self.labels_dict)] = [pred[p], p]
            res["label_predictions"] = category
            res["number_labels"] = len(pred)
            res["prediction"] = self.labelnum2text(np.argmax(pred), self.labels_dict)
            res["confidence"] = max(pred)
            res["label_num"] = np.argmax(pred)
            result.append(res)
        return result

    def label_conversion(self, labels):
        labels_dict = {}
        label_num = 0
        converted_labels = np.zeros(len(labels))
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

    def load_train_data(self, files, model_exists=False, load_test_data=False):
        err_tip = "<br>Try clearing training before loading more data!"
        data = []
        configs = []
        feature_lists = []
        frame_settings_list = []
        feature_map_dims = []
        for file in files:
            file_data = np.load(file, allow_pickle=True).item()
            data.append(file_data)
            configs.append(file_data["frame_data"]["sensor_config"])
            feature_lists.append(file_data["feature_list"])
            frame_settings_list.append(file_data["frame_settings"])
            feature_map_dims.append(
                file_data["frame_data"]["ml_frame_data"]["frame_list"][0]["feature_map"].shape
                )

        data_type = "training"
        if load_test_data:
            if self.labels_dict is None:
                return {"data": data, "success": False, "message": "Load train data first"}
            data_type = "test"

        if data_type == "training":
            self.model_params = {
                "feature_list": feature_lists[0],
                "frame_settings": frame_settings_list[0],
                "sensor_config": configs[0],
                "model_dimensions": self.model_dimensions,
                }
            if model_exists:
                self.model_dimensions["input"] = self.model.input_shape[1:-1]
                self.model_dimensions["output"] = self.model.output_shape[-1]
            else:
                self.model_dimensions["dimensionality"] = 2
                self.model_dimensions["input"] = feature_map_dims[0]
                if feature_map_dims[0][1] == 1:
                    self.model_dimensions["dimensionality"] = 1
        else:
            if self.model_params is None:
                message = "Load training data first!"
                return {"success": False, "message": message}

        for i in range(1, len(files)):
            # TODO: Check that files are compatible
            map_dims = self.model_dimensions["input"]
            if map_dims != feature_map_dims[i]:
                message = "Input dimenions not matching: <br> Model {} - Data {}".format(
                    map_dims,
                    feature_map_dims[i])
                message += err_tip
                return {"success": False, "message": message}

        labels = []
        feature_maps = []
        for d in data:
            fdata = d["frame_data"]["ml_frame_data"]["frame_list"]
            for data_idx in fdata:
                feature_maps.append(data_idx["feature_map"])
                labels.append(data_idx["label"])

        feature_map_data = np.stack(feature_maps)
        if self.model_dimensions["dimensionality"] == 2:
            feature_map_data = np.expand_dims(
                feature_map_data,
                self.model_dimensions["dimensionality"] + 1)

        if data_type == "training":
            data_labels, self.label_num, self.labels_dict = self.label_conversion(labels)
            if not model_exists:
                self.model_dimensions["output"] = self.label_num
            else:
                output = self.model_dimensions["output"]
                if self.label_num != output:
                    message = "Output dimenions not matching: <br> Model {} - Data {}".format(
                        output,
                        self.label_num)
                    message += err_tip
                    return {"success": False, "message": message}
        else:
            data_labels = self.label_assignment(labels, self.labels_dict)

        label_categories = to_categorical(data_labels, self.label_num)

        if data_type == "training":
            self.model_dimensions["init_shape"] = feature_map_data.shape[1:]
            print(self.model_dimensions)
            if not model_exists:
                self.clear_model(reinit=True)

        message = "Loaded {} data with shape {}<br>".format(data_type, feature_map_data.shape)
        message += "Found labels:<br>"
        for label in self.labels_dict:
            message += label + "<br>"

        data = {
            "x_data": feature_map_data,
            "y_labels": label_categories,
            "label_list": self.get_label_list(),
            "feature_list": self.model_params["feature_list"],
            "sensor_config": self.model_params["sensor_config"],
            "frame_settings": self.model_params["frame_settings"],
            "model_dimensions": self.model_params["model_dimensions"],
        }
        return {"data": data, "success": True, "message": message}

    def load_test_data(self, files):
        return self.load_train_data(files, load_test_data=True)

    def save_model(self, file, feature_list, sensor_config, frame_settings):
        try:
            info = {
                "labels_dict": self.labels_dict,
                "model_dimensions": self.model_dimensions,
                "feature_list": feature_list,
                "sensor_config": sensor_config,
                "model": self.model,
                "frame_settings": frame_settings,
            }
            np.save(file, info)
        except Exception as e:
            message = "Error saving model:<br>{}".format(e)
        else:
            message = None

        return message

    def load_model(self, file):
        try:
            del self.model
            info = np.load(file, allow_pickle=True)
            self.model = info.item()["model"]
            self.labels_dict = info.item()["labels_dict"]
            self.model_dimensions = info.item()["model_dimensions"]
            self.label_num = self.model_dimensions["output"]
            feature_list = info.item()["feature_list"]
            sensor_config = info.item()["sensor_config"]
            frame_settings = info.item()["frame_settings"]
            self.tf_session = K.get_session()
            self.tf_graph = tf.get_default_graph()
            with self.tf_session.as_default():
                with self.tf_graph.as_default():
                    self.model._make_predict_function()
        except Exception as e:
            error_text = self.format_error.error_to_text(e)
            message = "Error in load model:<br>{}".format(error_text)
            return {
                "loaded": False,
                "message": message,
                }
        else:
            message = "Loaded model with input shape:<br>{}<br>".format(self.model.input_shape)
            message += "Using {} features.".format(len(feature_list))

        return {
            "loaded": True,
            "message": message,
            "feature_list": feature_list,
            "sensor_config": sensor_config,
            "frame_settings": frame_settings,
            }

    def clear_model(self, reinit=False):
        if self.model is not None:
            K.clear_session()
            del self.model
            self.model = None

        if reinit and self.model_dimensions is not None:
            model_shape = self.model_dimensions["init_shape"]
            self.tf_session = K.get_session()
            self.tf_graph = tf.get_default_graph()
            with self.tf_session.as_default():
                with self.tf_graph.as_default():
                    if self.model_dimensions["dimensionality"] == 1:
                        self.init_model_1D(model_shape)
                    else:
                        self.init_model_2D(model_shape)

    def get_current_session(self, graph=None):
        return self.tf_session

    def get_current_graph(self):
        return self.tf_graph

    def set_current_session(self, session):
        K.set_session(session)

    def clear_training_data(self):
        self.model_params = None
        self.clear_model()

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


class TrainCallback(Callback):
    def __init__(self, plot_cb=None, steps_per_epoch=None, stop_cb=None):
        self.plot = plot_cb
        self.stop_cb = stop_cb
        self.steps_per_epoch = steps_per_epoch
        self.epoch = 0
        self.batch = 0

    def on_batch_end(self, batch, logs=None):
        self.batch += 1
        self.send_data(logs)

    def on_epoch_end(self, epoch, logs=None):
        self.epoch += 1
        self.send_data(logs)

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
    def __init__(self):
        self.first = True
        self.history = {
            "acc": [],
            "loss": [],
            "val_acc": [],
            "val_loss": [],
        }
        self.train_max = 1
        self.test_max = 1

    def setup(self, win):
        win.setWindowTitle("Keras training results")

        self.train_plot_window = win.addPlot(row=0, col=0, title="Training results")
        self.train_plot_window.showGrid(x=True, y=True)
        self.train_plot_window.addLegend(offset=(-10, 10))
        self.train_plot_window.setYRange(0, 1)
        self.train_plot_window.setXRange(0, 1)
        self.train_plot_window.setLabel("left", "Accuracy/Loss")
        self.train_plot_window.setLabel("bottom", "Epoch")

        self.progress_train = pg.TextItem(color="k", anchor=(0, 1), fill="#f0f0f0")
        self.progress_train.setPos(0, 0)
        self.progress_train.setZValue(2)
        self.train_plot_window.addItem(self.progress_train, ignoreBounds=True)

        self.test_plot_window = win.addPlot(row=1, col=0, title="Test-set results")
        self.test_plot_window.showGrid(x=True, y=True)
        self.test_plot_window.addLegend(offset=(-10, 10))
        self.test_plot_window.setYRange(0, 1)
        self.test_plot_window.setXRange(0, 1)
        self.test_plot_window.setLabel("left", "Accuracy/Loss")
        self.test_plot_window.setLabel("bottom", "Epoch")

        self.progress_test = pg.TextItem(color="k", anchor=(0, 1), fill="#f0f0f0")
        self.progress_test.setPos(0, 0)
        self.progress_test.setZValue(2)
        self.test_plot_window.addItem(self.progress_test, ignoreBounds=True)

        pen = example_utils.pg_pen_cycler(1)
        self.train_acc_plot = self.train_plot_window.plot(pen=pen, name="Accuracy")
        self.test_acc_plot = self.test_plot_window.plot(pen=pen, name="Accuracy")
        pen = example_utils.pg_pen_cycler(2)
        self.train_loss_plot = self.train_plot_window.plot(pen=pen, name="Loss")
        self.test_loss_plot = self.test_plot_window.plot(pen=pen, name="Loss")

    def process(self, data=None, flush_data=False):
        if flush_data:
            for hist in self.history:
                self.history[hist] = []
            self.progress_train.setText("")
            self.progress_test.setText("")
            self.train_max = 1
            self.test_max = 1

        if data is not None:
            for key in data:
                if key not in self.history:
                    self.history[key] = []
                self.history[key].append(data[key])

        self.update(self.history)

    def update(self, data):
        if data is None:
            return

        if not isinstance(data, dict):
            print("Train log data has wrong type: ", type(data))
            return

        train_x = None

        try:
            data_len = len(data["loss"])
            epoch = data_len
            spe = "N/A"
        except Exception as e:
            print("Cannot process training logs... ", e)
            return

        if not data_len:
            return

        batch = 0

        try:
            batch = data["batch"][-1] + 1
        except Exception:
            pass

        if "steps_per_epoch" in data:
            spe = data["steps_per_epoch"][0]
            increment = 1 / (spe + 1)
            epoch = np.ceil(data_len / spe)
            train_x = np.arange(0, epoch + increment, increment)
            train_x = train_x[0:data_len]
            epoch = int(epoch)

        acc = None
        loss = None
        val_acc = None
        val_loss = None

        for key in data:
            if "val_acc" in key:
                if len(data[key]):
                    val_acc = data[key][-1]
                self.test_acc_plot.setData(np.arange(1, len(data[key]) + 1), data[key])
            elif "val_loss" in key:
                if len(data[key]):
                    val_loss = data[key][-1]
                self.test_loss_plot.setData(np.arange(1, len(data[key]) + 1), data[key])
            elif "acc" in key:
                if len(data[key]):
                    acc = data[key][-1]
                if train_x is not None:
                    self.train_acc_plot.setData(train_x, data[key])
                else:
                    self.train_acc_plot.setData(np.arange(1, len(data[key]) + 1), data[key])
            elif "loss" in key:
                if len(data[key]):
                    loss = data[key][-1]
                if train_x is not None:
                    self.train_loss_plot.setData(train_x, data[key])
                else:
                    self.train_loss_plot.setData(np.arange(1, len(data[key]) + 1), data[key])

        p_train = "Epoch: {} Batch {} of {}\n".format(epoch, batch, spe)
        if acc is not None and loss is not None:
            p_train += "Acc: {:1.2E} Loss: {:1.2E}\n".format(acc, loss)
        self.progress_train.setText(p_train)

        if val_acc is not None and val_loss is not None:
            p_test = "Acc: {:1.2E} Loss: {:1.2E}\n".format(val_acc, val_loss)
            self.progress_test.setText(p_test)

        self.train_plot_window.setXRange(0, epoch)
        if acc and loss:
            train_max = max(acc, loss)
            if train_max > self.train_max:
                self.train_max = train_max
                self.train_plot_window.setYRange(0, train_max)
        self.test_plot_window.setXRange(0, epoch)
        if val_acc and val_loss:
            test_max = max(val_acc, val_loss)
            if test_max > self.test_max:
                self.test_max = test_max
                self.test_plot_window.setYRange(0, test_max)


class Arguments():
    def __init__(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("-l", "--load", dest="load",
                            help="Load training data", default="")
        parser.add_argument("-e", "--evaluate", dest="evaluate",
                            help="Sensor", default="")
        parser.add_argument("-sb", "--save-best", dest="save_best",
                            help="Save model", default=None)
        parser.add_argument("-s", "--save", dest="save",
                            help="Save model", default=None)
        parser.add_argument("-m", "--model", dest="model",
                            help="Load model", default=None)
        parser.add_argument("-t", "--train", dest="train",
                            help="Sensor", action="store_true")

        args = parser.parse_args()
        self.load = args.load
        self.save = args.save
        self.save_best = args.save_best
        self.train = args.train
        self.evaluate = args.evaluate
        self.model = args.model

    def get_args(self):
        return self


if __name__ == "__main__":
    arg = Arguments()
    args = arg.get_args()

    # TODO: add code for Deep learning without GUI
