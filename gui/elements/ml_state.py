from functools import partial

import numpy as np

from PyQt5 import QtCore, QtWidgets
from PyQt5.QtWidgets import QFrame, QLabel, QPushButton

import keras_processing as kp


class MLState:
    def __init__(self, parent):
        self.states = {
            "model_ready": False,
            "model_source": None,
            "training_data_ready": False,
            "training_data_files": [],
            "test_data_ready": False,
            "test_data_files": [],
            "settings_locked": False,
        }

        self.gui_handle = parent
        self.status_widgets = []
        self.model_data = {"loaded": False}
        self.keras_handle = kp.MachineLearning()

    def get_model_data(self):
        if not self.get_state("settings_locked"):
            gui = self.gui_handle
            self.model_data["frame_settings"] = gui.feature_sidepanel.get_frame_settings()
            self.model_data["feature_list"] = gui.feature_select.get_feature_list()
            self.model_data["sensor_config"] = gui.get_sensor_config()
        return self.model_data

    def get_model_source(self):
        return self.get_state("model_source")

    def get_model_status(self):
        return self.get_state("model_ready")

    def get_training_data_status(self):
        return self.get_state("training_data_ready")

    def get_test_data_status(self):
        return self.get_state("test_data_ready")

    def get_frame_settings(self, from_gui=True):
        if from_gui:
            return self.gui_handle.feature_sidepanel.get_frame_settings()
        else:
            if self.get_model_status():
                return self.get_model_data()["frame_settings"]
            else:
                return None

    def get_feature_list(self, from_gui=False):
        if from_gui:
            return self.gui_handle.feature_select.get_feature_list()
        else:
            if self.get_model_status():
                return self.get_model_data()["feature_list"]
            else:
                return None

    def get_ml_settings_for_scan(self, mode, params):
        is_eval_mode = (mode == "eval")
        load_from_gui = not is_eval_mode
        gui = self.gui_handle
        if is_eval_mode:
            if not self.get_model_status():
                gui.error_message("Please load a model first!\n")
                return False
            if not gui.ml_model_ops.config_is_valid():
                return False
        else:
            params["sweep_buffer"] = np.inf

        frame_settings = self.get_frame_settings(from_gui=load_from_gui)
        feature_list = self.get_feature_list(from_gui=load_from_gui)

        if frame_settings is None or feature_list is None:
            return False

        if mode == "feature_select":
            frame_settings["frame_pad"] = 0
            frame_settings["collection_mode"] = "continuous"
            frame_settings["rolling"] = True

        ml_settings = {
            "feature_list": feature_list,
            "frame_settings": frame_settings,
            "evaluate": is_eval_mode,
        }
        if is_eval_mode:
            ml_settings["evaluate_func"] = gui.ml_model_ops.predict
            gui.ml_eval_model_plot_widget.reset_data(
                params["sensor_config"],
                params["service_params"]
            )
        elif mode == "feature_extract":
            e_handle = gui.error_message
            if not gui.feature_select.check_limits(params["sensor_config"], error_handle=e_handle):
                return False
            gui.ml_feature_plot_widget.reset_data(
                params["sensor_config"],
                params["service_params"]
            )

        params["ml_settings"] = ml_settings

        return True

    def set_model_data(self, model_data, source="internal"):
        if model_data is None:
            state = False
            source = None
            self.model_data = {"loaded": False}
        else:
            state = model_data["loaded"]
            self.model_data = model_data
        self.set_state("settings_locked", state)
        self.set_state("model_file", source)
        self.set_state("model_ready", state)

    def set_training_data_status(self, loaded, list_of_files=[]):
        self.set_state("training_data_ready", loaded)
        self.set_state("training_data_files", list_of_files)

    def set_test_data_status(self, loaded, list_of_files=[]):
        self.set_state("test_data_ready", loaded)
        self.set_state("test_data_files", list_of_files)

    def set_state(self, state, value):
        if state in self.states:
            self.states[state] = value

        if state == "model_ready":
            if value:
                text = "Ready"
                in_out_text = "{} --> {}".format(
                    self.model_data["model_input"],
                    self.model_data["model_output"]
                )
            else:
                text = "Not initialized"
                in_out_text = "N/A"
            self.set_state("settings_locked", value)
            self.gui_handle.set_gui_state("ml_model_loaded", value)
            self.update_widgets(state, text)
            self.update_widgets("model_in_out", in_out_text)

        elif state == "model_file":
            self.states["model_source"] = value
            if value is None:
                value = "N/A"
            self.update_widgets(state, value)

        elif state == "training_data_files":
            if len(value):
                text = "{} files loaded".format(len(value))
            else:
                text = "Not loaded"
            self.update_widgets(state, text)

        elif state == "test_data_files":
            if len(value):
                text = "{} files loaded".format(len(value))
            else:
                text = "Not loaded"
            self.update_widgets(state, text)

        elif state == "settings_locked":
            if value:
                text = "Settings locked!"
                c = "red"
            else:
                text = "Settings unlocked!"
                c = "black"
            self.update_widgets("locked_status", text, color=c)

        if self.states["model_ready"] and self.states["training_data_ready"]:
            next_text = "Eval. or train"
        elif self.states["model_ready"] and not self.states["training_data_ready"]:
            next_text = "Eval. or load training"
        elif not self.states["model_ready"] and self.states["training_data_ready"]:
            next_text = "Update model layers"
        else:
            next_text = "Load training or model"

        self.update_widgets("next_step", next_text)

    def get_state(self, state):
        if state in self.states:
            return self.states[state]
        else:
            print("MLState: Unknown state {} requtested".format(state))
            return None

    def add_status_widget(self, widget):
        self.status_widgets.append(widget)

    def update_widgets(self, label, text, color=None):
        for w in self.status_widgets:
            if label in w.labels:
                w.labels[label].setText(text)
                if color is not None:
                    w.labels[label].setStyleSheet("color: {}".format(color))
            else:
                print("Status label {} not found".format(label))


class MLStateWidget(QFrame):
    def __init__(self, parent):
        super().__init__(parent)
        self.keras = None

        self.gui_handle = parent

        main_grid = QtWidgets.QGridLayout()
        main_grid.setContentsMargins(1, 1, 1, 1)
        self.setLayout(main_grid)

        self.info_widget = QFrame(self)
        info_grid = QtWidgets.QGridLayout()
        self.info_widget.setLayout(info_grid)

        self.button_widget = QFrame(self)
        button_grid = QtWidgets.QGridLayout()
        self.button_widget.setLayout(button_grid)

        self.labels = {
            "locked_status": QLabel("Settings editable"),
            "model_header:": QLabel("Model: "),
            "model_ready": QLabel("Not initialized"),
            "model_dims": QLabel("In/Out: "),
            "model_in_out": QLabel("N/A"),
            "model_source": QLabel("Source: "),
            "model_file": QLabel("N/A"),
            "training_header": QLabel("Training data: "),
            "training_data_files": QLabel("Not loaded"),
            "test_header": QLabel("Test data: "),
            "test_data_files": QLabel("Not loaded"),
            "next": QLabel("Next: "),
            "next_step": QLabel("Load train data or model"),
        }

        self.buttons = {
            "unlock": QPushButton("Unlock settings"),
            "load_model": QPushButton("Load Model"),
            "save_model": QPushButton("Save Model"),
            "remove_model": QPushButton("Remove Model"),
        }
        self.buttons["unlock"].clicked.connect(self.unlock)
        self.buttons["load_model"].clicked.connect(partial(self.model_ops, "load_model"))
        self.buttons["save_model"].clicked.connect(partial(self.model_ops, "save_model"))
        self.buttons["remove_model"].clicked.connect(partial(self.model_ops, "remove_model"))

        self.labels["next_step"].setStyleSheet("color: green")
        self.labels["model_file"].setWordWrap(True)
        self.labels["model_file"].setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)

        info_grid.addWidget(self.labels["model_header:"], 0, 0)
        info_grid.addWidget(self.labels["model_ready"], 0, 1)
        info_grid.addWidget(self.labels["model_dims"], 0, 2)
        info_grid.addWidget(self.labels["model_in_out"], 0, 3)
        info_grid.addWidget(self.labels["model_source"], 0, 4)
        info_grid.addWidget(self.labels["model_file"], 0, 5, 2, 1)
        info_grid.addWidget(self.labels["training_header"], 1, 0)
        info_grid.addWidget(self.labels["training_data_files"], 1, 1)
        info_grid.addWidget(self.labels["test_header"], 1, 2)
        info_grid.addWidget(self.labels["test_data_files"], 1, 3)
        info_grid.addWidget(self.labels["next"], 2, 0)
        info_grid.addWidget(self.labels["next_step"], 2, 1)

        info_grid.setColumnStretch(5, 2)

        button_grid.addWidget(self.labels["locked_status"], 0, 0)
        button_grid.addWidget(self.buttons["load_model"], 0, 1)
        button_grid.addWidget(self.buttons["save_model"], 1, 1)
        button_grid.addWidget(self.buttons["remove_model"], 0, 2)
        button_grid.addWidget(self.buttons["unlock"], 1, 2)

        main_grid.addWidget(self.info_widget, 0, 0)
        main_grid.addWidget(self.button_widget, 0, 1)
        main_grid.setColumnStretch(0, 2)

    def unlock(self):
        self.gui_handle.set_gui_state("ml_overwrite_settings", True)

    def model_ops(self, op):
        self.gui_handle.ml_model_ops.model_operation(op)
