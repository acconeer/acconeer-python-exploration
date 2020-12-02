import os
import traceback

import numpy as np
import tensorflow as tf
from keras import backend as K
from keras import optimizers as Opt
from keras.callbacks import Callback, EarlyStopping
from keras.layers import Input, TimeDistributed
from keras.models import Model
from keras.utils import to_categorical
from sklearn.model_selection import train_test_split
from sklearn.utils import class_weight

from acconeer.exptool import configs

import gui.ml.layer_definitions as layer_definitions
import gui.ml.ml_helper as ml_helper


not_time_distributed = [
    "GaussianNoise",
    "Dropout",
    "BatchNormalization",
    "LSTM",
]


class ACC_ML(ml_helper.KerasBase):
    tf_graph = None
    tf_session = None

    def init_model(self):
        input_dim = self.model_data.feature_dimension
        output_dim = self.model_data.output

        if not isinstance(input_dim, list):
            input_dim = list(input_dim)

        print("\nInitiating model with {:d}x{:d} inputs"
              " and {:d} outputs".format(*input_dim, output_dim))

        layer_list = self.model_data.layer_list
        if layer_list is None:
            print("No layers defined!")
            return {"loaded": False, "model_message": "No Layers defined"}

        nr_layers = len(layer_list)
        layer_callbacks = layer_definitions.get_layers()

        lstm_mode = False
        time_series = False
        steps = self.model_data.time_distributed
        print("Building model with {} layers...".format(nr_layers))
        if steps > 1:
            input_dim[-1] = input_dim[-1] - steps + 1
            input_dim = [steps] + input_dim
            lstm_mode = True
            time_series = True
            print("Building TimeDistributed model with {} steps!".format(steps))

        # Add single channel dimension
        if input_dim[-1] != 1:
            input_dim = input_dim + [1]

        self.model_data.input = input_dim

        inputs = Input(shape=input_dim)

        x = None
        nr_layers = len(layer_list)
        for idx, layer in enumerate(layer_list):
            if not layer.get("is_active", True):
                continue
            try:
                cb = layer_callbacks[layer['name']]['class']
            except KeyError:
                print("Layer {} not found in layer_definitions.py!".format(layer['name']))

            # Wrap layers in TimeDistributed until first LSTM layer
            if layer['name'] == "lstm":
                lstm_mode = False
                time_series = False
                layer["params"].pop("steps")
            if lstm_mode:
                if layer['class'] not in not_time_distributed:
                    time_series = True
                else:
                    time_series = False

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
                    if time_series:
                        x = TimeDistributed(cb(**options))(inputs)
                    else:
                        x = cb(**options)(inputs)
                elif idx > 0 and idx < nr_layers - 1:
                    if time_series:
                        x = TimeDistributed(cb(**options))(x)
                    else:
                        x = cb(**options)(x)
                else:
                    options.pop("units", None)
                    predictions = cb(output_dim, **options)(x)
            except Exception as e:
                traceback.print_exc()
                return {
                    "loaded": False,
                    "model_message": "\nLayer nr. {} failed."
                                     " Error adding {}\n{}".format(idx + 1, layer['name'], e)
                }

            if layer["name"] == "lstm":
                layer["params"]["steps"] = steps

        self.model = Model(inputs=inputs, outputs=predictions)

        self.set_optimizer("Adam")

        self.count_variables()

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
        plot_cb = train_params.get("plot_cb", None)
        stop_cb = train_params.get("stop_cb", None)
        save_best = train_params.get("save_best", None)
        steps = int(np.ceil(x.shape[0] / batch_size))
        func = TrainCallback(plot_cb=plot_cb,
                             steps_per_epoch=steps,
                             stop_cb=stop_cb,
                             save_best=save_best,
                             parent=self)
        cb.append(func)

        if plot_cb is not None:
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
                                                  verbose=verbose,
                                                  mode="auto"
                                                  )
                cb.append(cb_early_stop)

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
        if isinstance(x, str):
            if self.training_data["loaded"]:
                # Predict training data
                x = self.training_data["x_data"]
            else:
                print("No training data available!")
                return None

        if len(x.shape) == len(self.model.input_shape) - 1:
            if x.shape[0] == self.model.input_shape[1]:
                x = np.expand_dims(x, 0)
            else:
                x = np.expand_dims(x, -1)
        if len(x.shape) == len(self.model.input_shape) - 2:
            x = np.expand_dims(x, 0)
            x = np.expand_dims(x, -1)

        if len(x.shape) != len(self.model.input_shape):
            print("Wrong data shapes:\n Model: {}\n Test: {}\n".format(self.model.input_shape,
                                                                       x.shape,))
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

    def save_model(self, file, feature_list=None, sensor_config=None, frame_settings=None):
        if feature_list is None:
            feature_list = self.model_data.feature_list
        if sensor_config is None:
            sensor_config = self.model_data.sensor_config
        if frame_settings is None:
            frame_settings = self.model_data.frame_settings

        try:
            model_dimensions = {
                "input": self.model_data.input,
                "output": self.model_data.output,
                "time_distributed": self.model_data.time_distributed,
                "feature_dimension": self.model_data.feature_dimension,
            }
            info = {
                "labels_dict": self.labels_dict,
                "model_dimensions": model_dimensions,
                "feature_list": feature_list,
                "sensor_config": sensor_config._dumps(),
                "model": self.model,
                "frame_settings": frame_settings,
                "nr_of_training_maps": self.model_data.nr_of_training_maps,
            }
            np.save(file, info)
        except Exception as e:
            message = "Error saving model:\n{}".format(e)
        else:
            message = None

        return message

    def load_model(self, file):
        try:
            self.clear_model()
            info = np.load(file, allow_pickle=True)
            self.model = info.item()["model"]
            self.labels_dict = info.item()["labels_dict"]
            model_dimensions = info.item()["model_dimensions"]
            self.label_num = model_dimensions["output"]
            feature_list = info.item()["feature_list"]
            sensor_config = configs.load(info.item()["sensor_config"])
            frame_settings = info.item()["frame_settings"]
            time_distributed = model_dimensions.get("time_distributed", 1)
            feature_dimension = model_dimensions.get(
                "feature_dimension",
                model_dimensions["input"][:-1]
            )
            self.tf_session = K.get_session()
            self.tf_graph = tf.compat.v1.get_default_graph()
            with self.tf_session.as_default():
                with self.tf_graph.as_default():
                    self.model._make_predict_function()
        except Exception as e:
            error_text = self.error_to_text(e)
            message = "Error in load model:\n{}".format(error_text)
            return {"loaded": False}, message
        else:
            try:
                self.model_data.nr_of_training_maps = info.item()["nr_of_training_maps"]
            except KeyError:
                self.model_data.nr_of_training_maps = 0
            gui_layer_conf = layer_definitions.get_layers()
            layer_list = []
            for l in self.model.layers:
                l_conf = l.get_config()
                l_name = l_conf["name"].rsplit("_", 1)[0]
                if "time_distributed" in l_name:
                    l_conf = l_conf["layer"]["config"]
                    l_name = l_name = l_conf["name"].rsplit("_", 1)[0]
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

        model_data = {
            "loaded": True,
            "y_labels": label_categories,
            "label_list": labels,
            "feature_list": feature_list,
            "sensor_config": sensor_config,
            "frame_settings": frame_settings,
            "layer_list": layer_list,               # GUI format layer list
            "keras_layer_info": self.model.layers,  # Keras format layer list
            "input": model_dimensions["input"],
            "output": model_dimensions["output"],
            "time_distributed": time_distributed,
            "feature_dimension": feature_dimension,
        }

        self.set_model_data(model_data)
        self.count_variables()

        message = "Loaded model with:\n"
        message += "input shape    :{}\n".format(self.model_data.input)
        if self.model_data.time_distributed > 1:
            message += "time steps     :{}\n".format(self.model_data.time_distributed)
        message += "output shape   :{}\n".format(self.model_data.output)
        message += "nr of features :{}\n".format(len(feature_list))
        message += "labels         :{}\n".format(labels)
        message += "Trained with {} features".format(
                      self.model_data.get("nr_of_training_maps", "N/A")
                  )

        return self.model_data, message

    def clear_session(self):
        K.clear_session()
        tf.keras.backend.clear_session()

    def clear_model(self, reinit=False):
        if self.model is not None:
            self.clear_session()
            del self.model
            self.model = None
        if not reinit:
            for data in self.model_data:
                if data != "tf_version":
                    self.model_data[data] = None
            self.model_data.loaded = False
            self.label_num = 0
            self.time_distributed = 1
            self.labels_dict = None

        if reinit:
            self.tf_session = K.get_session()
            self.tf_graph = tf.compat.v1.get_default_graph()
            with self.tf_session.as_default():
                with self.tf_graph.as_default():
                    status = self.init_model()
                    if status["loaded"]:
                        self.model_data["loaded"] = True
                    return status
        else:
            return {"loaded": False, "model_message": "Nothing to reinitialize!"}

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

    def get_current_session(self, graph=None):
        return self.tf_session

    def get_current_graph(self):
        return self.tf_graph

    def set_current_session(self, session):
        K.set_session(session)

    def count_variables(self):
        if self.model is not None:
            trainable = int(
                np.sum([K.count_params(p) for p in set(self.model.trainable_weights)]))
            non_trainable = int(
                np.sum([K.count_params(p) for p in set(self.model.non_trainable_weights)]))
        else:
            return None

        return ({"trainable": trainable, "non_trainable": non_trainable})

    def clear_training_data(self):
        self.model_data.y_labels = None
        self.training_data = {"loaded": False}
        self.test_data = {"loaded": False}
        if not self.model_data.loaded:
            self.label_num = 0
            self.labels_dict = None

    def convert_to_categorical(self, labels, label_nr):
        return to_categorical(labels, label_nr)


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
