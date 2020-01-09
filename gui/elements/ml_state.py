from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QFrame, QLabel

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
        }

        self.gui_handle = parent
        self.status_widgets = []
        self.model_data = {"loaded": False}
        self.keras_handle = kp.MachineLearning()

    def get_model_data(self):
        return self.model_data

    def get_model_source(self):
        return self.get_state("model_source")

    def get_model_status(self):
        return self.get_state("model_ready")

    def get_training_data_status(self):
        return self.get_state("training_data_ready")

    def get_test_data_status(self):
        return self.get_state("test_data_ready")

    def set_model_data(self, model_data, source="internal"):
        state = True
        if model_data is None:
            state = False
            source = None
            self.model_data = {"loaded": False}
        else:
            self.model_data = model_data
        self.set_state("model_ready", state)
        self.set_state("model_file", source)

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

        if self.states["model_ready"] and self.states["training_data_ready"]:
            next_text = "Eval. or train"
        elif self.states["model_ready"] and not self.states["training_data_ready"]:
            next_text = "Eval. or load training"
        elif not self.states["model_ready"] and self.states["training_data_ready"]:
            next_text = "Update model layers"
        else:
            next_text = "Load training or model"
        self.update_widgets("next_step", next_text)

        allow_edit = False
        if self.states["model_source"] == "internal" or self.states["model_source"] is None:
            allow_edit = True
        self.gui_handle.model_select.allow_layer_edit(allow_edit)

    def get_state(self, state):
        if state in self.states:
            return self.states[state]
        else:
            print("Unknown state {} requtested from {}".format(state, self.sender()))
            return None

    def add_status_widget(self, widget):
        self.status_widgets.append(widget)

    def update_widgets(self, label, text):
        for w in self.status_widgets:
            if label in w.labels:
                w.labels[label].setText(text)
            else:
                print("Status label {} not found".format(label))


class MLStateWidget(QFrame):
    def __init__(self, parent, gui_handle):
        super().__init__(parent)
        self.keras = None

        self.gui_handle = gui_handle
        self.grid = QtWidgets.QGridLayout(self)
        self.grid.setContentsMargins(9, 0, 9, 9)

        self.labels = {
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

        self.labels["next_step"].setStyleSheet("color: green")
        self.labels["model_file"].setWordWrap(True)

        self.grid.addWidget(self.labels["model_header:"], 0, 0)
        self.grid.addWidget(self.labels["model_ready"], 0, 1)
        self.grid.addWidget(self.labels["model_dims"], 1, 0)
        self.grid.addWidget(self.labels["model_in_out"], 1, 1)
        self.grid.addWidget(self.labels["model_source"], 2, 0)
        self.grid.addWidget(self.labels["model_file"], 2, 1)
        self.grid.addWidget(self.labels["training_header"], 3, 0)
        self.grid.addWidget(self.labels["training_data_files"], 3, 1)
        self.grid.addWidget(self.labels["test_header"], 4, 0)
        self.grid.addWidget(self.labels["test_data_files"], 4, 1)
        self.grid.addWidget(self.labels["next"], 5, 0)
        self.grid.addWidget(self.labels["next_step"], 5, 1)
