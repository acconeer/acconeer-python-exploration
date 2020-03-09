import colorsys
import datetime
import os
import sys
import time
import traceback
from functools import partial

import numpy as np
import pyqtgraph as pg
import yaml

from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from acconeer.exptool import configs, recording, utils
from acconeer.exptool.modes import Mode

import feature_definitions as feature_def
import feature_processing as feature_proc
import keras_processing as kp
import layer_definitions as layer_def
from helper import Count, ErrorFormater, LoadState, QHLine, QVLine, SensorSelection
from modules import MODULE_KEY_TO_MODULE_INFO_MAP


HERE = os.path.dirname(os.path.realpath(__file__))
HERE = os.path.abspath(os.path.join(HERE, '..'))
DEFAULT_MODEL_FILENAME_2D = os.path.join(HERE, "ml", "default_layers_2D.yaml")
TRAIN_TAB = 5
FEATURE_EXTRACT_TAB = 2
REMOVE_BUTTON_STYLE = (
    "QPushButton:pressed {background-color: red;}"
    "QPushButton:hover:!pressed {background-color: lightcoral;}"
)


class FeatureSelectFrame(QFrame):
    def __init__(self, parent, gui_handle=None):
        super().__init__(parent)
        self.param_col = 2
        self.sensor_col = self.param_col + 2
        self.remove_col = self.sensor_col + 2
        self.nr_col = self.remove_col + 1
        self.row_idx = Count(2)
        self.gui_handle = gui_handle
        self.has_valid_config = False
        self.feature_testing = False
        self.sweeps_per_frame = None

        self.limits = {
            "start": 0,
            "end": np.inf,
            "sensors": [1, 2, 3, 4],
            "data_type": Mode.ENVELOPE,
            "model_dimension": 2,
        }

        self._grid = QtWidgets.QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(0)
        self.setLayout(self._grid)

        self.main = QtWidgets.QSplitter(self)
        self.main.setOrientation(QtCore.Qt.Vertical)
        self.main.setStyleSheet("QSplitter::handle{background: lightgrey}")
        self._grid.addWidget(self.main)

        self.feature_frame_scroll = QtWidgets.QScrollArea(self.main)
        self.feature_frame_scroll.setFrameShape(QFrame.NoFrame)
        self.feature_frame_scroll.setWidgetResizable(True)
        self.feature_frame_scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.feature_frame_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.feature_frame_scroll.setMinimumWidth(1000)
        self.feature_frame_scroll.setMinimumHeight(350)

        self.feature_frame = QFrame(self.feature_frame_scroll)
        self.feature_frame_scroll.setWidget(self.feature_frame)

        self.main.addWidget(self.feature_frame_scroll)
        self.f_layout = QtWidgets.QGridLayout(self.feature_frame)
        self.f_layout.setContentsMargins(2, 2, 2, 2)
        self.f_layout.setSpacing(5)
        self.feature_frame.setLayout(self.f_layout)

        self.enabled_features = []
        self.features = feature_def.get_features()

        self.enabled_count = Count()
        self.create_grid()
        self.parse_features()
        self.create_feature_plot()
        self._grid.setRowStretch(0, 1)

        self.drop_down.setCurrentIndex(1)

    def create_grid(self):
        self.f_layout.addWidget(QLabel("Feature"), 0, 0)
        self.f_layout.addWidget(QLabel("Parameters"), 0, self.param_col)
        self.f_layout.addWidget(QLabel("Sensors"), 0, self.sensor_col)
        self.f_layout.addWidget(QHLine(), 1, 0, 1, self.nr_col)
        self.name_vline = QVLine()
        self.params_vline = QVLine()
        self.sensor_vline = QVLine()

        self.buttons = {
            "start": QPushButton("Test extraction"),
            "stop": QPushButton("Stop"),
            "replay_buffered": QPushButton("Replay buffered"),
            "set_to_feature": QPushButton("Sensor to Feature"),
            "set_to_sensor": QPushButton("Feature to Sensor"),
        }

        self.drop_down = QComboBox()
        self.drop_down.addItem("Add feature")

        self.bottom_widget = QFrame()
        self.bottom_widget.setFrameStyle(QFrame.Panel | QFrame.Raised)
        bottom_box = QHBoxLayout()
        bottom_box.setAlignment(QtCore.Qt.AlignLeft)
        self.bottom_widget.setLayout(bottom_box)
        bottom_box.addWidget(self.drop_down)
        bottom_box.addWidget(self.buttons["start"])
        bottom_box.addWidget(self.buttons["stop"])
        bottom_box.addWidget(self.buttons["replay_buffered"])
        bottom_box.addStretch(1)
        bottom_box.addWidget(QLabel("Match sensor settings:"))
        bottom_box.addWidget(self.buttons["set_to_feature"])
        bottom_box.addWidget(self.buttons["set_to_sensor"])

        self._grid.addWidget(self.bottom_widget)

        for b in self.buttons:
            button = self.buttons[b]
            if "set" not in b:
                button.clicked.connect(partial(self.gui_handle.buttons[b].click))
                button.setEnabled(False)
            else:
                button.clicked.connect(self.match_settings)

    def update_grid(self):
        try:
            self.f_layout.removeWidget(self.name_vline)
            self.f_layout.removeWidget(self.params_vline)
            self.f_layout.removeWidget(self.sensor_vline)
        except Exception:
            pass

        self.f_layout.addWidget(self.name_vline, 0, 1, self.row_idx.val + 1, 1)
        self.f_layout.addWidget(self.params_vline, 0, self.param_col + 1, self.row_idx.val + 1, 1)
        self.f_layout.addWidget(self.sensor_vline, 0, self.sensor_col + 1, self.row_idx.val + 1, 1)

        self.drop_down.setCurrentIndex(0)

        self.f_layout.setRowStretch(self.row_idx.val + 3, 1)
        self.f_layout.setColumnStretch(self.nr_col, 1)

        self.update_feature_plot()

    def allow_feature_edit(self, allow):
        self.feature_frame.setEnabled(allow)
        self.drop_down.setEnabled(allow)

    def increment(self, skip=[1]):
        self.num += 1
        self.increment_skip(skip)
        return self.num

    def increment_skip(self, skip):
        if self.num in skip:
            self.num += 1
            self.increment(skip=skip)
        return self.num

    def parse_features(self):
        self.feature_list = {}
        self.name_to_key = {}

        for key in self.features:
            try:
                feat = self.features[key]
                name = feat["name"]
                self.feature_list[key] = {
                    "name": name,
                    "cb": feat["class"],
                    "options": {},
                    "output": None,
                    "model": int(feat["model"][0]),
                    "data_type": feat["data_type"],
                }
                self.name_to_key[name] = key
            except Exception as e:
                print("Failed to add feature!\n", e)

        for key in self.feature_list:
            self.drop_down.addItem(self.feature_list[key]["name"])

        self.drop_down.currentIndexChanged.connect(self.add_features_details)

    def add_features_details(self, data, key=None):
        if not key:
            index = self.sender().currentIndex()
            if index == 0:
                return
            else:
                try:
                    key = self.name_to_key[self.sender().currentText()]
                except KeyError:
                    print("Unknown feature: {}\n".format(self.sender().currentText()))
                    return
                except Exception as e:
                    print("Something went wrong!\n", e)
                    return

        feat = self.features[key]
        name = feat["name"]
        cb = feat["class"]
        model = feat["model"][0]
        sensor_data_type = feat["data_type"]

        feat_cb = cb()
        output, opts = feat_cb.get_options()

        size_cb = None
        try:
            size_cb = feat_cb.get_size
        except Exception:
            pass

        labels = {}
        textboxes = {}

        self.num = 0
        row = self.row_idx.pre_incr()

        other_items = []
        other_items.append(QLabel(name))
        self.f_layout.addWidget(other_items[0], row, self.num)
        c = utils.color_cycler(self.enabled_count.pre_incr())
        other_items[0].setStyleSheet("background-color: {}".format(c))

        options_widget = QWidget(self)
        options_box = QHBoxLayout()
        options_box.setAlignment(QtCore.Qt.AlignLeft)
        options_widget.setLayout(options_box)
        self.f_layout.addWidget(options_widget, row, self.param_col)
        options = {}
        gui_conf = self.gui_handle.get_sensor_config()
        for (text, value, limits, data_type) in opts:
            labels[text] = QLabel(text)
            if data_type == bool:
                textboxes[text] = QCheckBox(self)
                textboxes[text].setChecked(value)
                edit = textboxes[text].stateChanged
            else:
                textboxes[text] = QLineEdit(str(value))
                if text == "Start" and gui_conf is not None:
                    textboxes[text].setText(str(gui_conf.range_start))
                if text == "Stop" and gui_conf is not None:
                    textboxes[text].setText(str(gui_conf.range_end))
                edit = textboxes[text].editingFinished
            edit.connect(
                partial(self.update_feature_params, limits, data_type, value)
            )
            options[text] = textboxes[text]
            options_box.addWidget(labels[text])
            options_box.addWidget(textboxes[text])

        sensors = SensorSelection(
            multi_sensors=True,
            error_handler=None,
            callback=self.update_feature_plot
        )
        available_sensors = [1]
        try:
            available_sensors = self.gui_handle.get_sensors()
        except Exception:
            pass
        sensors.set_sensors(available_sensors)

        self.f_layout.addWidget(sensors, row, self.sensor_col)

        c_button = QPushButton("remove", self)
        c_button.setStyleSheet(REMOVE_BUTTON_STYLE)
        c_button.clicked.connect(self.remove_feature)

        self.f_layout.addWidget(c_button, row, self.remove_col)

        row = self.row_idx.pre_incr()

        other_items.append(QLabel("Output [{}D]".format(model)))
        self.f_layout.addWidget(other_items[1], row, 0)

        output_widget = QWidget(self)
        output_box = QHBoxLayout()
        output_box.setAlignment(QtCore.Qt.AlignLeft)
        output_widget.setLayout(output_box)
        self.f_layout.addWidget(output_widget, row, self.param_col)
        out_data = {}
        for idx, o in enumerate(output):
            out_data[o] = QCheckBox(output[o], self)
            out_data[o].stateChanged.connect(self.update_feature_plot)
            output_box.addWidget(out_data[o])
            if idx == 0:
                out_data[o].setChecked(True)
            if len(output) == 1:
                out_data[o].setVisible(False)

        other_items.append(QHLine())

        self.f_layout.addWidget(other_items[2], self.row_idx.pre_incr(), 0, 1, self.nr_col)

        feature_params = {
            "name": name,
            "cb": cb,
            "options": options,
            "output": out_data,
            "sensors": sensors,
            "textboxes": textboxes,
            "labels": labels,
            "other_items": other_items,
            "c_button": c_button,
            "count": self.enabled_count.val,
            "size_cb": size_cb,
            "model_dimension": model,
            "sensor_data_type": sensor_data_type,
            "options_box": options_box,
            "options_widget": options_widget,
            "output_box": output_box,
            "output_widget": output_widget,
        }

        self.enabled_features.append(feature_params)

        self.update_grid()

    def remove_feature(self, clear_all=False):
        if not clear_all:
            button = self.sender()
            button_idx = self.f_layout.indexOf(button)
            pos = self.f_layout.getItemPosition(button_idx)
            list_pos = [int((pos[0] - 2) / 3)]
        else:
            list_pos = list(range(len(self.enabled_features)))

        pop_list = []
        for lpos in list_pos:
            for idx, feature in enumerate(self.enabled_features):

                if idx < lpos:
                    continue

                options_widgets = []
                output_widgets = []
                widgets = []
                widgets.append(feature["sensors"])
                widgets.append(feature["c_button"])
                widgets.append(feature["options_widget"])
                widgets.append(feature["output_widget"])

                for i in feature["other_items"]:
                    widgets.append(i)

                for key in feature["textboxes"]:
                    options_widgets.append(feature["textboxes"][key])
                    options_widgets.append(feature["labels"][key])

                for key in feature["output"]:
                    output_widgets.append(feature["output"][key])

                if idx == lpos:
                    for w in widgets:
                        self.f_layout.removeWidget(w)
                        w.deleteLater()
                        w = None
                else:
                    for w in widgets:
                        idx = self.f_layout.indexOf(w)
                        pos = self.f_layout.getItemPosition(idx)
                        self.f_layout.removeWidget(w)
                        self.f_layout.addWidget(w, pos[0] - 3, pos[1], pos[2], pos[3])

            pop_list.append(lpos)
            self.row_idx.decr(val=3)
            if len(pop_list) == len(self.enabled_features):
                self.row_idx.set_val(1)

        pop_list.sort(reverse=True)
        for i in pop_list:
            self.enabled_features.pop(i)

        self.update_grid()

    def get_feature_list(self, enabled_features=None):
        f_list = []

        list_of_sensors = []
        sensor_data_types = []
        model_dimensions = []
        min_start = np.inf
        max_end = 0

        if enabled_features is None:
            enabled_features = self.enabled_features
        if not isinstance(enabled_features, list):
            enabled_features = [enabled_features]

        for idx, feat in enumerate(enabled_features):
            key = self.name_to_key[feat["name"]]
            entry = {}
            entry["key"] = key
            entry["name"] = feat["name"]
            entry["sensors"] = feat["sensors"].get_sensors()

            for s in entry["sensors"]:
                if s not in list_of_sensors:
                    list_of_sensors.insert(s - 1, s)

            entry["options"] = {}
            if feat["options"] is not None:
                for opt in feat["options"]:
                    opt_cb = feat["options"][opt]
                    if isinstance(opt_cb, QtWidgets.QCheckBox):
                        entry["options"][opt] = opt_cb.isChecked()
                    else:
                        entry["options"][opt] = float(opt_cb.text())
                    if opt == "Start":
                        start = float(opt_cb.text())
                        if start < min_start:
                            min_start = start
                    if opt == "Stop":
                        end = float(opt_cb.text())
                        if end > max_end:
                            max_end = end

            entry["output"] = {}
            if feat["output"] is not None:
                for out in feat["output"]:
                    out_cb = feat["output"][out]
                    if out_cb == "enabled":
                        entry["output"][out] = True
                    else:
                        entry["output"][out] = out_cb.isChecked()

            if feat["model_dimension"] not in model_dimensions:
                model_dimensions.append(feat["model_dimension"])
            if feat["sensor_data_type"] not in sensor_data_types:
                sensor_data_types.append(feat["sensor_data_type"])

            entry["model_dimension"] = int(feat["model_dimension"])

            f_list.append(entry)

        self.limits = {
            "start": min_start,
            "end": max_end,
            "sensors": list_of_sensors,
            "model_dimensions": model_dimensions,
            "sensor_data_types": sensor_data_types,
        }

        return f_list

    def match_settings(self):
        action = self.sender().text()

        # Update Limits
        self.get_feature_list()

        if action == "Sensor to Feature":
            sensor_conf = self.gui_handle.get_sensor_config()
            if sensor_conf is None:
                return
            for feature in self.enabled_features:
                if "Start" in feature["options"]:
                    feature["options"]["Start"].setText(str(sensor_conf.range_start))
                if "Stop" in feature["options"]:
                    feature["options"]["Stop"].setText(str(sensor_conf.range_end))
                feature["sensors"].set_sensors(sensor_conf.sensor)
        elif action == "Feature to Sensor":
            if len(self.enabled_features) == 0:
                return
            module_key = self.limits["sensor_data_types"][0].value
            module_info = MODULE_KEY_TO_MODULE_INFO_MAP[module_key]
            index = self.gui_handle.module_dd.findText(
                module_info.label,
                QtCore.Qt.MatchFixedString
            )
            if index != self.gui_handle.module_dd.currentIndex():
                message = "Do you want to change the service to {}?".format(module_key)
                if self.gui_handle.warning_message(message):
                    self.gui_handle.module_dd.setCurrentIndex(index)
                    self.gui_handle.update_canvas()
            conf = self.gui_handle.get_sensor_config()
            conf.sensor = self.limits["sensors"]
            try:
                conf.range_interval = [self.limits["start"], self.limits["end"]]
            except Exception:
                # This error needs to be actively fixed by the user in the GUI.
                pass
        else:
            print("Action {} not supported!.".format(action))

        self.update_feature_plot()

    def update_feature_list(self, saved_feature_list):
        # check if feature list is valid
        for feat in saved_feature_list:
            feature = {}
            feature["key"] = feat["key"]
            feature["name"] = feat["name"]
            feature["class"] = self.features[feat["key"]]["class"]
            feature["sensors"] = feat["sensors"]

        self.remove_feature(clear_all=True)

        error_message = "Feature Classes not found:\n"
        all_found = True
        for feature in saved_feature_list:
            try:
                feature_key = feature["key"]
                self.add_features_details(None, key=feature_key)
            except Exception:
                error_message += ("Feature Name:\n{}\n".format(feature["name"]))
                all_found = False
            else:
                if feature_key in self.feature_list:
                    e_feat = self.enabled_features[-1]
                    e_feat["sensors"].set_sensors(feature["sensors"])

                    if feature["options"] is not None:
                        for opt in feature["options"]:
                            if opt in ["sensor_config", "session_info"]:
                                continue
                            try:
                                opt_textbox = e_feat["options"][opt]
                                if not isinstance(opt_textbox, QtWidgets.QCheckBox):
                                    opt_textbox.setText(str(feature["options"][opt]))
                                elif isinstance(opt_textbox, QtWidgets.QCheckBox):
                                    opt_textbox.setChecked(feature["options"][opt])
                            except Exception:
                                # May fail if feature code has changed
                                traceback.print_exc()
                                print("Failed to set feature option!")
                    if feature["output"] is not None:
                        for out in feature["output"]:
                            out_checkbox = e_feat["output"][out]
                            out_checkbox.setChecked(feature["output"][out])

        if not all_found:
            try:
                self.gui_handle.error_message(error_message)
            except Exception:
                print(error_message)

        self.update_feature_plot()

        return all_found

    def update_sensors(self, sensor_config):
        try:
            sensors = sensor_config.sensor
        except Exception:
            return

        for feat in self.enabled_features:
            feat["sensors"].set_sensors(sensors)

    def update_sensor_config(self, sensor_config):
        self.sensor_config = sensor_config

    def check_limits(self, sensor_config=None, error_handle=None):
        QApplication.processEvents()
        if sensor_config is None:
            sensor_config = self.gui_handle.save_gui_settings_to_sensor_config()

        # Update limits
        self.get_feature_list()

        if len(self.enabled_features) == 0:
            self.has_valid_config = False
            self.set_error_text("No features added!")
            return False

        feat_start = self.limits["start"]
        feat_end = self.limits["end"]
        feat_sensors = self.limits["sensors"]
        feature_data_types = self.limits["sensor_data_types"]
        model_dimensions = self.limits["model_dimensions"]
        error_message = None

        if len(feat_sensors) == 0:
            self.set_error_text("No sensor input configured!")
            self.has_valid_config = False
            return False

        config_is_valid = {
            "start": [feat_start, None, False],
            "end": [feat_end, None, False],
            "sensors": [feat_sensors, None, False],
        }

        try:
            config_start = sensor_config.range_start
            config_end = sensor_config.range_end
            config_sensors = sensor_config.sensor
            config_data_type = sensor_config.mode
            self.sweeps_per_frame = None
            if config_data_type == Mode.SPARSE:
                self.sweeps_per_frame = sensor_config.sweeps_per_frame
        except Exception:
            if error_handle is None:
                return self.set_error_text("No service selected!")
            else:
                error_handle("Sensor_config has wrong format!")
                return False

        is_valid = True
        if feat_start > feat_end:
            if error_message is None:
                error_message = "Configuration mismatch:\n"
            error_message += "Feature start must be less than feature end!\n"
            is_valid = False

        config_is_valid["start"][1] = config_start
        if feat_start >= config_start and feat_start < config_end:
            config_is_valid["start"][2] = True

        config_is_valid["end"][1] = config_end
        if feat_end <= config_end:
            config_is_valid["end"][2] = True

        config_is_valid["sensors"][1] = config_sensors
        config_is_valid["sensors"][2] = True

        for sensor in feat_sensors:
            if sensor not in config_sensors:
                config_is_valid["sensors"][2] = False
                break

        for k in config_is_valid:
            if not config_is_valid[k][2]:
                if error_message is None:
                    error_message = "Configuration mismatch:\n"
                error_message += "Settings for {}:\n Features:\n{}\nSensor:\n{}\n".format(
                    k,
                    config_is_valid[k][0],
                    config_is_valid[k][1],
                )
                is_valid = False

        if len(model_dimensions) > 1:
            is_valid = False
            err = "Features with different dimensions:\n"
            if error_message is None:
                error_message = err
            else:
                error_message += err
            error_message += "{}\n".format(model_dimensions)

        data_types_valid = True
        if Mode.SPARSE in feature_data_types and config_data_type != Mode.SPARSE:
            data_types_valid = False
        if Mode.IQ in feature_data_types and config_data_type != Mode.IQ:
            data_types_valid = False
        if Mode.IQ in feature_data_types and Mode.SPARSE in feature_data_types:
            data_types_valid = False

        if not data_types_valid:
            is_valid = False
            err = "Inconsistent sensor data types\n"
            if error_message is None:
                error_message = err
            else:
                error_message += err
            error_message += "Features:\n"
            for d in feature_data_types:
                error_message += "{} ".format(d)
            error_message += "\nSensor:\n{}\n".format(config_data_type)

        if not is_valid:
            self.buttons["start"].setEnabled(False)
            self.buttons["replay_buffered"].setEnabled(False)
            self.has_valid_config = False
            if error_handle is None:
                self.set_error_text(error_message)
            else:
                error_handle(error_message)
            return False
        else:
            self.has_valid_config = True
            if self.gui_handle.get_gui_state("server_connected"):
                self.buttons["start"].setEnabled(True)
                if self.gui_handle.data is not None:
                    self.buttons["replay_buffered"].setEnabled(True)
            self.set_error_text()
            return True

    def is_config_valid(self):
        return self.has_valid_config

    def clearLayout(self):
        while self.f_layout.count():
            child = self.f_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def create_feature_plot(self):
        info_plot_frame = QFrame(self)
        grid = QtWidgets.QGridLayout()
        info_plot_frame.setLayout(grid)
        grid.setContentsMargins(2, 2, 10, 0)
        grid.setSpacing(0)
        self.main.addWidget(info_plot_frame)

        win = pg.GraphicsLayoutWidget()
        win.setWindowTitle("Feature plotting")
        self.feat_plot_image = win.addPlot(row=0, col=0)
        self.feat_plot_image.setLabel("left", "Features")
        self.feat_plot_image.setLabel("bottom", "Sweeps")
        self.feat_plot_image.setXRange(0, 30)
        self.feat_plot_image.setYRange(0, 1)
        self.feat_plot_image.showGrid(True, False)
        self.feat_dim_text = pg.TextItem(color="k", anchor=(0, 1), fill="#f0f0f0")
        self.feat_dim_text.setPos(0, 0)
        self.feat_dim_text.setZValue(3)
        self.feat_plot_image.addItem(self.feat_dim_text)

        self.feat_plot = pg.ImageItem()
        self.feat_plot.setAutoDownsample(True)
        self.feat_plot_image.addItem(self.feat_plot)

        lut = utils.pg_mpl_cmap("viridis")
        self.feat_plot.setLookupTable(lut)

        self.feature_areas = []
        grid.addWidget(win, 0, 0, 2, 1)
        info_header = QLabel("Configuration status:")
        info_header.setFixedWidth(200)
        info_header.setFixedHeight(20)
        info_header.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        self.error_text = QLabel()
        self.error_text.setFixedWidth(200)
        self.error_text.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        self.error_text.setWordWrap(True)
        grid.addWidget(info_header, 0, 1)
        grid.addWidget(self.error_text, 1, 1)
        self.set_error_text("No service selected")

    def set_error_text(self, text=None):
        if text is None:
            self.error_text.setStyleSheet("QLabel {color: green}")
            self.error_text.setText("Ready to collect features")

        else:
            self.error_text.setStyleSheet("QLabel {color: red}")
            self.error_text.setText(text)

    def update_feature_params(self, limits, data_type, default):
        if data_type != bool:
            out_of_limits = False
            val = -1
            try:
                val = data_type(self.sender().text())
            except Exception:
                out_of_limits = True

            if limits is not None:
                if isinstance(limits, list) and len(limits) == 2:
                    if val < limits[0]:
                        val = limits[0]
                        out_of_limits = True
                    if val > limits[1]:
                        val = limits[1]
                        out_of_limits = True

            if out_of_limits:
                self.sender().setText(str(default))

        self.update_feature_plot()
        return

    def update_feature_plot(self):
        self.check_limits()
        for area in self.feature_areas:
            self.feat_plot_image.removeItem(area)

        scan_is_running = self.gui_handle.get_gui_state("scan_is_running")
        if not scan_is_running:
            self.feat_plot.setOpacity(0)

        self.feature_areas = []

        frame_size = self.get_frame_size()

        self.feat_plot_image.setXRange(0, max(frame_size, 1))

        y_max_size = 0
        x_max_size = 0
        for feature in self.enabled_features:
            nr_sensors = len(feature["sensors"].get_sensors())
            feature_opts = self.get_feature_list([feature])[0]["options"]
            feature_size = 1
            if feature["size_cb"] is not None:
                if self.sweeps_per_frame:
                    feature_opts["sweeps_per_frame"] = self.sweeps_per_frame
                feature_size = feature["size_cb"](feature_opts)
            out_multiplier = 0
            for out in feature["output"]:
                output_enabled = feature["output"][out].isChecked()
                if output_enabled:
                    out_multiplier += 1
            feature_size *= out_multiplier

            if feature_size:
                for i in range(nr_sensors):
                    x_size = int(feature["model_dimension"][0])
                    if x_size == 2:
                        x_size = frame_size
                    if x_size > x_max_size:
                        x_max_size = x_size
                    rect = pg.QtGui.QGraphicsRectItem(0, y_max_size, x_size, feature_size)
                    rect.setPen(utils.pg_pen_cycler(feature["count"]))
                    rect.setBrush(utils.pg_brush_cycler(feature["count"]))
                    rect.setOpacity(0.5)
                    rect.setZValue(2)
                    self.feat_plot_image.addItem(rect)
                    self.feature_areas.append(rect)
                    y_max_size += feature_size

        self.feature_testing = False

        self.feat_plot_image.setYRange(0, max(y_max_size, 1))

        self.feat_dim_text.setText("Feature size: {} by {}".format(int(y_max_size), x_max_size))

        if scan_is_running and self.has_valid_config:
            self.gui_handle.sig_scan.emit("update_feature_list", None, self.get_feature_list())
            self.feature_testing = False

    def plot_feature(self, data):
        feat_map = None
        if data["ml_frame_data"] is not None:
            frame_data = data["ml_frame_data"]
            feat_map = frame_data["current_frame"]["feature_map"]
        else:
            return

        if feat_map is None:
            return

        if not self.feature_testing:
            self.feature_testing = True
            for area in self.feature_areas:
                area.setBrush(QBrush(QtCore.Qt.NoBrush))
                area.setOpacity(1)
            self.feat_plot.setOpacity(1)

        ymax_level = 1.2 * np.max(feat_map)

        g = 1/2.2
        feat_map = 254/(ymax_level + 1.0e-9)**g * feat_map**g

        feat_map[feat_map > 254] = 254

        self.feat_plot.updateImage(feat_map.T, levels=(0, 256))
        self.feat_plot_image.setYRange(0, feat_map.shape[0])

        return

    def get_frame_size(self):
        if hasattr(self.gui_handle, "feature_sidepanel"):
            frame_size = self.gui_handle.feature_sidepanel.get_frame_settings()["frame_size"]
        else:
            frame_size = 30

        return frame_size


class FeatureExtractFrame(QFrame):
    def __init__(self, parent, gui_handle=None):
        super().__init__(parent)

        self.gui_handle = gui_handle

        self.grid = QtWidgets.QGridLayout()
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(0)
        self.setLayout(self.grid)

        self.plot_widget = None
        self.nr_col = 3

        self.labels = {
            "label": QLabel("Label: "),
            "empty_1": QLabel(""),
            "empty_2": QLabel(""),
            "empty_3": QLabel(""),
            "empty_4": QLabel(""),
        }
        self.textboxes = {
            "label": QLineEdit("name_of_label"),
        }
        self.h_lines = {
            "h_line_1": QHLine(),
        }

        self.textboxes["label"].setAlignment(QtCore.Qt.AlignHCenter)
        self.labels["label"].setFixedWidth(200)
        self.labels["empty_2"].setFixedWidth(200)

        self.grid.addWidget(self.labels["empty_1"], 0, 0, 1, self.nr_col)
        self.grid.addWidget(self.labels["label"], 1, 0)
        self.grid.addWidget(self.textboxes["label"], 1, 1)
        self.grid.addWidget(self.labels["empty_2"], 1, 2)
        self.grid.addWidget(self.labels["empty_3"], 2, 0, 1, self.nr_col)
        self.grid.addWidget(self.h_lines["h_line_1"], 3, 0, 1, self.nr_col)
        self.grid.addWidget(self.labels["empty_4"], 4, 0, 1, self.nr_col)

    def init_graph(self):
        if self.gui_handle.current_module_label == "Select service":
            self.gui_handle.module_dd.setCurrentIndex(2)

        feature_canvas = pg.GraphicsLayoutWidget()
        self.plot_widget = feature_proc.PGUpdater(
            self.gui_handle.save_gui_settings_to_sensor_config(),
            self.gui_handle.update_service_params()
        )
        self.plot_widget.setup(feature_canvas)

        self.grid.addWidget(feature_canvas, 5, 0, 1, self.nr_col)

    def set_label(self, label):
        self.textboxes["label"].setText(str(label))

    def get_label(self):
        return self.textboxes["label"].text()


class FeatureSidePanel(QFrame):
    sig_scan = pyqtSignal(str, str, object)

    def __init__(self, parent, gui_handle):
        super().__init__(parent)

        self.gui_handle = gui_handle
        self.ml_state = gui_handle.ml_state
        self.grid = QtWidgets.QGridLayout()
        self.grid.setContentsMargins(9, 0, 9, 9)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)
        self.setLayout(self.grid)
        self.last_filename = None
        self.last_folder = None
        self.file_list = None

        self.format_error = ErrorFormater()

        self.frame_settings = {}

        self.labels = {
            "frame_time": QLabel("Frame time [s]"),
            "update_rate": QLabel("Update rate [Hz]"),
            "frame_size": QLabel("Sweeps per frame"),
            "auto_thrshld_offset": QLabel("Thrshld/Offset:"),
            "dead_time": QLabel("Dead time:"),
            "save_load": QLabel("Save/load session data:"),
            "batch_header": QLabel("Batch process session data:"),
            "frame_settings": QLabel("Frame settings:"),
            "collection_mode": QLabel("Feature collection mode:"),
            "empty_1": QLabel(""),
            "empty_2": QLabel(""),
            "empty_3": QLabel(""),
            "loaded_file": QLabel(""),
        }

        self.textboxes = {
            "frame_time": QLineEdit(str(1)),
            "update_rate": QLineEdit(str(30)),
            "frame_size": QLineEdit(str(30)),
            "auto_threshold": QLineEdit("1.5"),
            "dead_time": QLineEdit("10"),
            "auto_offset": QLineEdit("5"),
        }

        self.h_lines = {
            "h_line_1": QHLine(),
            "h_line_2": QHLine(),
            "h_line_3": QHLine(),
            "h_line_4": QHLine(),
        }

        self.buttons = {
            "load_session": QPushButton("Load session"),
            "save_session": QPushButton("Save session"),
            "trigger": QPushButton("&Trigger"),
            "create_calib": QPushButton("Create calibration"),
            "show_calib": QPushButton("Show calibration"),
            "load_batch": QPushButton("Load batch"),
            "process_batch": QPushButton("Process batch"),
        }

        self.buttons["load_session"].clicked.connect(self.load_data)
        self.buttons["create_calib"].clicked.connect(self.calibration_handling)
        self.buttons["show_calib"].clicked.connect(self.calibration_handling)
        self.buttons["save_session"].clicked.connect(self.save_data)
        self.buttons["load_batch"].clicked.connect(self.batch_process)
        self.buttons["process_batch"].clicked.connect(self.batch_process)
        self.buttons["trigger"].clicked.connect(
            lambda: self.gui_handle.sig_scan.emit(
                "update_feature_extraction",
                "triggered",
                True
            )
        )
        self.buttons["show_calib"].setEnabled(False)
        self.buttons["process_batch"].setEnabled(False)

        self.checkboxes = {
            "rolling": QCheckBox("Rolling frame"),
        }
        self.checkboxes["rolling"].clicked.connect(
            partial(self.frame_settings_storage, "rolling")
        )

        self.radiobuttons = {
            "auto": QRadioButton("auto"),
            "single": QRadioButton("single"),
            "continuous": QRadioButton("cont."),
        }

        self.auto_mode = QComboBox()
        self.auto_mode.addItem("Presence detection")
        self.auto_mode.addItem("Feature detection")

        self.radiobuttons["auto"].setChecked(True)
        self.radio_frame = QFrame()
        self.radio_frame.grid = QtWidgets.QGridLayout()
        self.radio_frame.grid.setContentsMargins(0, 0, 0, 0)
        self.radio_frame.setLayout(self.radio_frame.grid)
        self.radio_frame.grid.addWidget(self.labels["collection_mode"], 0, 0, 1, 3)
        self.radio_frame.grid.addWidget(self.h_lines["h_line_2"], 1, 0, 1, 3)
        self.radio_frame.grid.addWidget(self.radiobuttons["auto"], 2, 0)
        self.radio_frame.grid.addWidget(self.radiobuttons["single"], 2, 1)
        self.radio_frame.grid.addWidget(self.radiobuttons["continuous"], 2, 2)
        self.radio_frame.grid.addWidget(self.checkboxes["rolling"], 3, 0, 1, 2)
        self.radio_frame.grid.addWidget(self.buttons["trigger"], 4, 0, 1, 3)
        self.radio_frame.grid.addWidget(self.auto_mode, 5, 0, 1, 3)
        self.radio_frame.grid.addWidget(self.labels["auto_thrshld_offset"], 6, 0)
        self.radio_frame.grid.addWidget(self.textboxes["auto_threshold"], 6, 1)
        self.radio_frame.grid.addWidget(self.textboxes["auto_offset"], 6, 2)
        self.radio_frame.grid.addWidget(self.labels["dead_time"], 7, 0)
        self.radio_frame.grid.addWidget(self.textboxes["dead_time"], 7, 1, 1, 2)

        for toggle in self.radiobuttons:
            self.radiobuttons[toggle].toggled.connect(
                partial(self.frame_settings_storage, "collection_mode")
            )
        self.textboxes["auto_threshold"].editingFinished.connect(
            partial(self.frame_settings_storage, "auto_threshold")
        )
        self.textboxes["dead_time"].editingFinished.connect(
            partial(self.frame_settings_storage, "dead_time")
        )
        self.textboxes["auto_offset"].editingFinished.connect(
            partial(self.frame_settings_storage, "auto_offset")
        )
        self.auto_mode.currentIndexChanged.connect(
            partial(self.frame_settings_storage, "collection_mode")
        )
        self.frame_settings_storage()

        for key in self.textboxes:
            if key in ["auto_threshold", "dead_time", "auto_offset"]:
                continue
            tag = key
            self.textboxes[key].editingFinished.connect(partial(self.calc_values, tag, False))
            self.textboxes[key].textChanged.connect(partial(self.calc_values, tag, True))

        self.num = 0
        self.grid.addWidget(self.labels["frame_settings"], self.increment(), 0, 1, 2)
        self.grid.addWidget(self.h_lines["h_line_1"], self.increment(), 0, 1, 2)
        self.grid.addWidget(self.labels["frame_time"], self.increment(), 0)
        self.grid.addWidget(self.textboxes["frame_time"], self.num, 1)
        self.grid.addWidget(self.labels["update_rate"], self.increment(), 0)
        self.grid.addWidget(self.textboxes["update_rate"], self.num, 1)
        self.grid.addWidget(self.labels["frame_size"], self.increment(), 0)
        self.grid.addWidget(self.textboxes["frame_size"], self.num, 1)
        self.grid.addWidget(self.buttons["create_calib"], self.increment(), 0)
        self.grid.addWidget(self.buttons["show_calib"], self.num, 1)
        self.grid.addWidget(self.labels["empty_1"], self.increment(), 0, 1, 2)
        self.grid.addWidget(self.radio_frame, self.increment(), 0, 1, 2)
        self.grid.addWidget(self.labels["empty_2"], self.increment(), 0, 1, 2)
        self.grid.addWidget(self.labels["save_load"], self.increment(), 0, 1, 2)
        self.grid.addWidget(self.h_lines["h_line_3"], self.increment(), 0, 1, 2)
        self.grid.addWidget(self.buttons["load_session"], self.increment(), 0)
        self.grid.addWidget(self.buttons["save_session"], self.num, 1)
        self.grid.addWidget(self.labels["loaded_file"], self.increment(), 0, 1, 2)
        self.grid.addWidget(self.labels["empty_3"], self.increment(), 0, 1, 2)
        self.grid.addWidget(self.labels["batch_header"], self.increment(), 0, 1, 2)
        self.grid.addWidget(self.h_lines["h_line_4"], self.increment(), 0, 1, 2)
        self.grid.addWidget(self.buttons["load_batch"], self.increment(), 0)
        self.grid.addWidget(self.buttons["process_batch"], self.num, 1)

        self.textboxes["frame_size"].setEnabled(False)
        self.textboxes["update_rate"].setEnabled(False)

        self.grid.setRowStretch(self.increment(), 1)

        # Hide these elements
        self.modes = {
            "feature_select": [
                self.radio_frame,
                self.labels["empty_2"],
            ],
            "feature_extract": [
                self.labels["empty_1"],
                self.h_lines["h_line_1"],
                self.labels["frame_settings"],
                self.labels["frame_time"],
                self.labels["update_rate"],
                self.labels["frame_size"],
                self.textboxes["frame_time"],
                self.textboxes["update_rate"],
                self.textboxes["frame_size"],
                self.buttons["create_calib"],
                self.buttons["show_calib"],
            ],
            "feature_inspect": [
                self.labels["frame_time"],
                self.labels["update_rate"],
                self.labels["batch_header"],
                self.labels["empty_3"],
                self.h_lines["h_line_4"],
                self.textboxes["frame_time"],
                self.textboxes["update_rate"],
                self.labels["empty_1"],
                self.buttons["load_batch"],
                self.buttons["process_batch"],
                self.radio_frame,
            ],
            "eval": [
                self.labels["empty_1"],
                self.labels["empty_2"],
                self.labels["empty_3"],
                self.labels["frame_settings"],
                self.labels["save_load"],
                self.labels["frame_time"],
                self.labels["update_rate"],
                self.labels["frame_size"],
                self.labels["loaded_file"],
                self.labels["batch_header"],
                self.h_lines["h_line_1"],
                self.h_lines["h_line_3"],
                self.h_lines["h_line_4"],
                self.textboxes["frame_time"],
                self.textboxes["update_rate"],
                self.textboxes["frame_size"],
                self.buttons["load_session"],
                self.buttons["save_session"],
                self.buttons["create_calib"],
                self.buttons["show_calib"],
                self.buttons["load_batch"],
                self.buttons["process_batch"],
            ],
            "train": [],
        }

    def frame_settings_storage(self, senders=None):
        all_senders = [
            "frame_label",
            "frame_size",
            "collection_mode",
            "auto_threshold",
            "auto_offset",
            "dead_time",
            "rolling",
            "update_rate",
            "calibration",
        ]
        if senders is None:
            senders = all_senders
        elif not isinstance(senders, list):
            senders = [senders]

        for sender in senders:
            try:
                if sender == "frame_label":
                    self.frame_settings[sender] = self.gui_handle.feature_extract.get_label()
                elif sender in ["frame_size", "dead_time", "auto_offset"]:
                    self.frame_settings[sender] = int(self.textboxes[sender].text())
                elif sender in ["frame_time", "update_rate", "auto_threshold"]:
                    self.frame_settings[sender] = float(self.textboxes[sender].text())
                elif sender == "rolling":
                    self.frame_settings[sender] = self.checkboxes[sender].isChecked()
            except Exception as e:
                print("Wrong settings for {}:\n{}".format(sender, e))

            if sender == "collection_mode":
                self.frame_settings["collection_mode"] = self.radio_toggles()

        # ToDo: Complete frame padding functionality
        self.frame_settings["frame_pad"] = 0

        if self.frame_settings["frame_size"] <= 0:
            print("Warning: Frame size must be larger than 0!")
            self.frame_settings["frame_size"] = 1

        sig = None
        if self.gui_handle.get_gui_state("scan_is_running"):
            sig = self.gui_handle.sig_scan

            # Only allow hot updating frame size when feature select preview
            if self.gui_handle.get_gui_state("ml_tab") == "feature_select":
                senders = ["frame_size"]

            # Make sure to update collection mode properly
            if len(senders) == 1:
                if senders[0] in ["rolling", "collection_mode"]:
                    senders = all_senders

            if len(senders) > 1:
                sig.emit("update_feature_extraction", None, self.frame_settings)
            else:
                sig.emit("update_feature_extraction", senders[0], self.frame_settings[senders[0]])

    def get_frame_settings(self):
        self.frame_settings_storage()
        return self.frame_settings

    def set_frame_settings(self, frame_settings):
        try:
            if "frame_label" in frame_settings:
                self.gui_handle.feature_extract.set_label(frame_settings["frame_label"])
            if "frame_time" in frame_settings:
                self.textboxes["frame_time"].setText(str(frame_settings["frame_time"]))
            if "update_rate" in frame_settings:
                self.textboxes["update_rate"].setText(str(frame_settings["update_rate"]))
            if "dead_time" in frame_settings:
                self.textboxes["dead_time"].setText(str(frame_settings["dead_time"]))
            if "auto_threshold" in frame_settings:
                self.textboxes["auto_threshold"].setText(str(frame_settings["auto_threshold"]))
            if "auto_offset" in frame_settings:
                self.textboxes["auto_offset"].setText(str(frame_settings["auto_offset"]))
            if "collection_mode" in frame_settings:
                collection_mode = frame_settings["collection_mode"]
                if "auto" in collection_mode:
                    if "feature_based" in collection_mode:
                        self.auto_mode.setCurrentIndex(1)
                    else:
                        self.auto_mode.setCurrentIndex(0)
                    collection_mode = "auto"
                self.radiobuttons[collection_mode].setChecked(True)
            if "rolling" in frame_settings:
                self.checkboxes["rolling"].setChecked(frame_settings["rolling"])
            if frame_settings.get("calibration") is not None:
                if self.frame_settings.get("frame_settings") is not None:
                    print("Found calibration data in file. Overwriting existing calibration data")
                self.buttons["show_calib"].setEnabled(True)
                self.buttons["create_calib"].setText("Clear calibration")
                self.frame_settings["calibration"] = frame_settings["calibration"]
        except Exception as e:
            print(e)

        self.frame_settings_storage()

    def calc_values(self, key, edditing):
        try:
            frame_time = float(self.textboxes["frame_time"].text())
            update_rate = float(self.textboxes["update_rate"].text())
        except Exception:
            if not edditing:
                print("{} is not a valid input for {}!".format(self.textboxes[key].text(), key))
                if key == "frame_time":
                    self.textboxes["frame_time"].setText("1")
                if key == "update_rate":
                    sensor_config = self.gui_handle.get_sensor_config()
                    if sensor_config is None:
                        update_rate = "50.0"
                    else:
                        update_rate = "{:.1f}".format(sensor_config.update_rate)
                    self.textboxes["update_rate"].setText(update_rate)
                return
            else:
                return

        if not edditing:
            if frame_time == 0:
                self.textboxes["frame_time"].setText("1")
                frame_time = 1

        if key == "update_rate":
            sensor_config = self.gui_handle.get_sensor_config()
            if sensor_config is not None:
                sensor_config.update_rate = float(self.textboxes["update_rate"].text())

        sweeps = int(update_rate * frame_time)

        self.textboxes["frame_size"].setText(str(sweeps))

        self.frame_settings_storage([key, "frame_size"])

        self.gui_handle.feature_select.update_feature_plot()

        return

    def radio_toggles(self):
        self.checkboxes["rolling"].hide()
        self.buttons["trigger"].hide()
        self.labels["auto_thrshld_offset"].hide()
        self.textboxes["auto_threshold"].hide()
        self.labels["dead_time"].hide()
        self.textboxes["dead_time"].hide()
        self.textboxes["auto_offset"].hide()
        self.auto_mode.hide()

        if self.radiobuttons["auto"].isChecked():
            self.labels["auto_thrshld_offset"].show()
            self.textboxes["auto_threshold"].show()
            self.labels["dead_time"].show()
            self.textboxes["dead_time"].show()
            self.textboxes["auto_offset"].show()
            self.auto_mode.show()
        if self.radiobuttons["continuous"].isChecked():
            self.checkboxes["rolling"].show()
        if self.radiobuttons["single"].isChecked():
            self.buttons["trigger"].show()

        for m in self.radiobuttons:
            if self.radiobuttons[m].isChecked():
                if m == "auto" and "feature detection" in self.auto_mode.currentText().lower():
                    m = "auto_feature_based"
                break
        return m

    def increment(self):
        self.num += 1
        return self.num

    def select_mode(self, mode):
        for m in self.modes:
            for element in self.modes[m]:
                element.show()

        try:
            elements = self.modes[mode]
        except Exception:
            return

        for element in elements:
            element.hide()

        self.mode = mode

    def load_data(self):
        error_handle = self.gui_handle.error_message
        action = self.sender().text()
        title = "Load session data"
        if "settings" in action:
            title = "Load feature settings"
        elif "calibration" in action:
            title = "Load session file for frame calibration"

        options = QtWidgets.QFileDialog.Options()
        options |= QtWidgets.QFileDialog.DontUseNativeDialog
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, title, "", "NumPy data files (*.npy)", options=options)

        self.labels["loaded_file"].setText("")
        self.last_filename = None

        if filename:
            try:
                self.last_folder = os.path.split(filename)[0]
                data = np.load(filename, allow_pickle=True)
            except Exception as e:
                error_text = self.format_error.error_to_text(e)
                error_handle("Failed to load file:<br> {}".format(error_text))
                return
        else:
            return

        if "settings" in action:
            try:
                self.gui_handle.feature_select.update_feature_list(data.item()["feature_list"])
            except Exception as e:
                error_text = self.format_error.error_to_text(e)
                error_handle("Failed to load features from file:\n {}".format(error_text))
                return
        elif "calibration" in action:
            try:
                frame_list = data.item()["frame_data"]["ml_frame_data"]["frame_list"]
                nr_frames = len(frame_list)
                calibration = np.zeros_like(frame_list[0]["feature_map"])
                for frame in frame_list:
                    calibration += (frame["feature_map"] / nr_frames)
            except Exception as e:
                print("Failed to generate calibration array!<br>{}".format(e))
                return None
            else:
                return calibration
        else:
            try:
                sweep_data = recording.unpack(data.item()["sweep_data"])
                frame_data = data.item()["frame_data"]
                feature_list = data.item()["feature_list"]
                if self.ml_state.get_state("settings_locked"):
                    print("Settings locked, not loading feature list from file!")
                else:
                    self.gui_handle.feature_select.update_feature_list(feature_list)
                try:
                    self.gui_handle.feature_extract.set_label(
                        frame_data["ml_frame_data"]["current_frame"]["label"]
                    )
                except Exception as e:
                    error_text = self.format_error.error_to_text(e)
                    print("No label stored ({})".format(error_text))

                module_info = MODULE_KEY_TO_MODULE_INFO_MAP[sweep_data.module_key]
                index = self.gui_handle.module_dd.findText(
                    module_info.label,
                    QtCore.Qt.MatchFixedString
                )
                if index >= 0:
                    self.gui_handle.module_dd.setCurrentIndex(index)
                    self.gui_handle.update_canvas()

                data_len = len(sweep_data.data.data)
                conf = self.gui_handle.get_sensor_config()
                conf._loads(sweep_data.sensor_config_dump)
                frame_data["sensor_config"] = conf

                self.gui_handle.data = sweep_data
                self.gui_handle.ml_data = frame_data
                self.gui_handle.load_gui_settings_from_sensor_config(conf)
                self.gui_handle.textboxes["sweep_buffer"].setText(str(data_len))
                self.gui_handle.buttons["replay_buffered"].setEnabled(True)
                self.gui_handle.set_multi_sensors()
                self.gui_handle.set_sensors(conf.sensor)
                self.gui_handle.set_gui_state("load_state", LoadState.LOADED)
                self.gui_handle.feature_inspect.update_frame("frames", 1, init=True)
                self.gui_handle.feature_inspect.update_sliders()
                print("Found data with {} sweeps and {} feature frames.".format(
                    data_len,
                    len(frame_data["ml_frame_data"]["frame_list"]))
                )
            except Exception as e:
                error_text = self.format_error.error_to_text(e)
                error_handle("Failed to load data:<br> {}".format(error_text))
                return

        self.last_filename = os.path.split(filename)[1]
        self.labels["loaded_file"].setText(str(self.last_filename))

        try:
            frame_settings = data.item()["frame_settings"]
            self.gui_handle.feature_sidepanel.set_frame_settings(frame_settings)
        except Exception as e:
            error_text = self.format_error.error_to_text(e)
            error_handle("Failed to load frame settings:<br> {}".format(error_text))

    def save_data(self, filename=None, action="session"):
        feature_list = self.gui_handle.feature_select.get_feature_list()

        if action == "settings":
            title = "Save feature settings"
            fname = 'ml_feature_settings_{date:%Y_%m_%d_%H%M}'.format(date=datetime.datetime.now())
        elif action == "session":
            title = "Save session data"
            fname = 'ml_session_data_{date:%Y_%m_%d_%H%M}'.format(date=datetime.datetime.now())
            fname += "_{}".format(self.gui_handle.feature_extract.get_label())

        if self.last_folder is not None:
            fname = os.path.join(self.last_folder, fname)

        options = QtWidgets.QFileDialog.Options()
        options |= QtWidgets.QFileDialog.DontUseNativeDialog
        file_types = "NumPy data files (*.npy)"

        if not filename:
            filename, info = QtWidgets.QFileDialog.getSaveFileName(
                self, title, fname, file_types, options=options)

        if not filename:
            return
        self.last_folder = os.path.split(filename)[0]

        if action == "settings":
            data = {
                "feature_list": feature_list,
                "frame_settings": self.gui_handle.feature_sidepanel.get_frame_settings(),
            }

        elif action == "session":
            if self.gui_handle.data is None or self.gui_handle.ml_data is None:
                print("Missing data, cannot save session!")
                return

            record = self.gui_handle.data

            # Temporarily remove sensor_config object for saving
            sensor_config = self.gui_handle.ml_data.pop("sensor_config")

            packed_record = recording.pack(record)
            title = "Save session data"
            data = {
                "feature_list": self.gui_handle.ml_data["ml_frame_data"]["feature_list"],
                "sweep_data": packed_record,
                "frame_data": self.gui_handle.ml_data,
                "frame_settings": self.gui_handle.feature_sidepanel.get_frame_settings(),
                "sensor_config": record.sensor_config_dump,
            }

        try:
            np.save(filename, data, allow_pickle=True)
        except Exception as e:
            self.gui_handle.error_message("Failed to save settings:\n {}".format(e))

        # Restore sensor config object
        if action == "session":
            self.gui_handle.ml_data["sensor_config"] = sensor_config

        return

    def calibration_handling(self):
        action = self.sender().text().lower()

        show_data = None
        clear_data = None
        use_data = None

        if "show" in action:
            show_data = True
            calibration = self.frame_settings.get("calibration")
        elif "create" in action:
            calibration = self.load_data()
            if calibration is not None:
                show_data = True
            if len(np.where(calibration == 0.0)[0]):
                print("Warning, replacing 0 elements with 1!")
                print(np.where(calibration == 0.0)[0])
                calibration[np.where(calibration == 0)[0]] = 1
        elif "clear" in action:
            clear_data = True
            calibration = None

        if show_data and calibration is not None:
            dialog = CalibrationDialog(calibration.copy(), self)
            ret = dialog.exec_()
            if ret:
                use_data = True
            else:
                clear_data = True

        if calibration is None:
            clear_data = True

        if clear_data:
            if "calibration" in self.frame_settings:
                self.frame_settings.pop("calibration", None)
            self.buttons["show_calib"].setEnabled(False)
            self.buttons["create_calib"].setText("Create calibration")
        elif use_data:
            self.frame_settings["calibration"] = calibration
            self.buttons["show_calib"].setEnabled(True)
            self.buttons["create_calib"].setText("Clear calibration")

    def batch_process(self):
        action = self.sender().text().lower()
        if "load" in action:
            title = "Select files for batch processing"
            options = QtWidgets.QFileDialog.Options()
            options |= QtWidgets.QFileDialog.DontUseNativeDialog
            filenames, _ = QtWidgets.QFileDialog.getOpenFileNames(
                self, title, "", "NumPy data files (*.npy)", options=options)
            if filenames:
                self.file_list = filenames
                self.buttons["process_batch"].setEnabled(True)
            else:
                self.file_list = None
                self.buttons["process_batch"].setEnabled(False)
        else:
            if self.file_list is None:
                self.buttons["process_batch"].setEnabled(False)
                return

            dialog = BatchProcessDialog(self)
            dialog.exec_()

            batch_params = dialog.get_state()

            if not batch_params["process"]:
                return
            else:
                batch_params["file_list"] = self.file_list

            dialog.deleteLater()

            batch_params["gui_handle"] = self.gui_handle

            if batch_params["processing_mode"] == "all":
                self.gui_handle.tab_parent.setCurrentIndex(FEATURE_EXTRACT_TAB)

            self.threaded_batch_process = Threaded_BatchProcess(
                batch_params,
                self.gui_handle,
                parent=self
            )
            self.threaded_batch_process.sig_scan.connect(self.thread_receive)
            self.sig_scan.connect(self.threaded_batch_process.receive)
            self.threaded_batch_process.start()

            self.progress_bar = ProgressBar(self.threaded_batch_process.receive)
            self.progress_bar.exec_()
            self.threaded_batch_process.receive("stop", "", "")
            try:
                self.progress_bar.deleteLater()
            except Exception:
                # Might be closed elsewhere
                pass

    def thread_receive(self, message_type, message, data=None):
        if "update_data" in message_type:
            self.gui_handle.textboxes["sweep_buffer"].setText(str(data["sweep_buffer"]))
            self.gui_handle.buttons["replay_buffered"].setEnabled(data["replay_buffered"])
            self.gui_handle.set_sensors(data["sensors"])
            self.gui_handle.data = data["sweep_data"]
            self.gui_handle.ml_data = data["ml_data"]
        elif message_type == "start_scan":
            self.gui_handle.buttons["replay_buffered"].click()
        elif message_type == "stop_scan":
            self.gui_handle.buttons["stop"].click()
        elif message_type == "update_sensor_config":
            self.gui_handle.load_gui_settings_from_sensor_config(data)
            self.gui_handle.set_sensors(data.sensor)
        elif message_type == "set_module":
            self.gui_handle.module_dd.setCurrentIndex(data)
        elif message_type == "set_label":
            self.gui_handle.feature_extract.set_label(data)
        elif message_type == "update_progress":
            try:
                self.progress_bar.update_progress(data)
            except Exception:
                # Might have been closed already
                pass
        elif message_type == "update_file_info":
            self.progress_bar.update_file_info(data)
        elif message_type == "skipped_files":
            for skipped in data:
                print(skipped)
        elif message_type == "batch_process_stopped":
            try:
                self.progress_bar.close()
                self.progress_bar.deleteLater()
            except Exception:
                # Might be closed elsewhere
                pass
        elif message_type == "save_data":
            self.gui_handle.feature_sidepanel.save_data(filename=data)
        else:
            print("Thread data not implemented! {}".format(message_type))
            print(message_type, message, data)


class FeatureInspectFrame(QFrame):
    def __init__(self, parent, gui_handle=None):
        super().__init__(parent)

        self.current_sweep_nr = 0
        self.current_frame_nr = -1
        self.current_frame_data = None
        self.nr_col = 2

        self.feature_process = None
        self.gui_handle = gui_handle
        self.grid = QtWidgets.QGridLayout(self)
        self.grid.setContentsMargins(9, 0, 9, 9)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)
        self.setLayout(self.grid)

        self.graph = LabelingGraph(self)

        self.labels = {
            "update": QLabel("Update frame data: "),
            "current_frame": QLabel("Frame: NA"),
            "current_sweep": QLabel("Sweep: NA"),
            "label": QLabel("Label: ")
        }
        self.textboxes = {
            "label": QLineEdit("", self),
        }
        for t in self.textboxes:
            self.textboxes[t].setStyleSheet("background-color: white")

        self.checkboxes = {
        }

        self.sliders = {
            "sweep_slider": SpinBoxAndSliderWidget("Sweeps", callback=self.update_frame),
            "frame_slider": SpinBoxAndSliderWidget("Frames", callback=self.update_frame),
        }
        for s in self.sliders:
            self.sliders[s].set_limits([0, 100])

        self.buttons = {
            "update_to_current": QPushButton("to current frame", self),
            "update_to_new": QPushButton("to new frame", self),
            "update_to_none": QPushButton("remove frame", self),
            "write_to_all": QPushButton("Write label to all frames", self),
            "augment_data": QPushButton("Data augmentation", self),
        }

        for i in self.buttons:
            if "update" in i:
                self.buttons[i].clicked.connect(self.update_frame_data)
            elif "write" in i:
                self.buttons[i].clicked.connect(self.update_frame_labels)
        self.buttons["augment_data"].clicked.connect(self.augment_data)

        self.update_box = QFrame()
        self.update_box.grid = QtWidgets.QGridLayout(self.update_box)
        self.update_box.grid.addWidget(self.labels["label"], 0, 0, 1, 2)
        self.update_box.grid.addWidget(self.textboxes["label"], 1, 0, 1, 2)
        self.update_box.grid.addWidget(self.buttons["write_to_all"], 2, 0, 1, 2)
        self.update_box.grid.addWidget(self.labels["current_frame"], 4, 0)
        self.update_box.grid.addWidget(self.labels["current_sweep"], 4, 1)
        empty_1 = QLabel("")
        empty_1.setFixedWidth(10)
        empty_2 = QLabel("")
        empty_2.setFixedWidth(10)
        self.update_box.grid.addWidget(empty_1, 0, 2, 5, 1)
        self.update_box.grid.addWidget(QVLine(), 0, 3, 5, 1)
        self.update_box.grid.addWidget(empty_2, 0, 4, 5, 1)
        self.update_box.grid.addWidget(self.labels["update"], 0, 5)
        self.update_box.grid.addWidget(self.buttons["update_to_current"], 1, 5)
        self.update_box.grid.addWidget(self.buttons["update_to_new"], 2, 5)
        self.update_box.grid.addWidget(self.buttons["update_to_none"], 3, 5)
        self.update_box.grid.addWidget(self.buttons["augment_data"], 4, 5)
        self.update_box.setLayout(self.update_box.grid)
        self.update_box.setFrameStyle(QFrame.Panel | QFrame.Raised)
        self.update_box.grid.setRowStretch(10, 1)

        self.slider_box = QFrame()
        self.slider_box.grid = QtWidgets.QGridLayout(self.slider_box)
        self.slider_box.setLayout(self.slider_box.grid)
        self.slider_box.setFrameStyle(QFrame.Panel | QFrame.Raised)
        self.slider_box.grid.addWidget(self.sliders["sweep_slider"], 0, 0)
        self.slider_box.grid.addWidget(self.sliders["frame_slider"], 1, 0)

        self.num = 0
        self.grid.addWidget(QLabel(""), self.num, 0, 1, self.nr_col)
        self.grid.addWidget(self.update_box, self.increment(), 0)
        self.grid.addWidget(self.slider_box, self.num, 1)
        self.grid.addWidget(QLabel(""), self.increment(), 0, 1, self.nr_col)
        self.grid.addWidget(QHLine(), self.increment(), 0, 1, self.nr_col)
        self.grid.addWidget(QLabel(""), self.increment(), 0, 1, self.nr_col)
        self.grid.addWidget(self.graph, self.increment(), 0, 1, self.nr_col)

    def update_frame(self, action, number, init=False):
        action = action.lower()
        fdata = self.gui_handle.ml_data
        if fdata is None:
            print("No feature data available!")
            return

        f_histdata = fdata["ml_frame_data"]["frame_list"]

        frame_nr = self.current_frame_nr
        if action == "frames":
            frame_nr = max(0, number - 1)
        total_frames = len(f_histdata) - 1
        frame_nr = int(min(total_frames, frame_nr))

        if action == "frames" and frame_nr == self.current_frame_nr:
            if frame_nr != 0:
                return
        elif action == "sweeps" and number == self.current_sweep_nr:
            return

        record = self.gui_handle.data
        f_info = fdata["ml_frame_data"]["frame_info"]
        n_sweeps = len(record.data) - f_info["frame_size"] - 2 * f_info["frame_pad"]

        if frame_nr < 0:
            print("No feature data available!")
            return

        if action == "frames":
            self.set_slider_value("frame_slider", frame_nr + 1)
            f_current = f_histdata[frame_nr]
            for key in f_histdata[frame_nr]:
                f_current[key] = f_histdata[frame_nr][key]
                fdata["ml_frame_data"]["current_frame"][key] = f_histdata[frame_nr][key]
            label = f_current["label"]
            self.current_frame_data = f_current

            try:
                if init:
                    self.graph.reset_data()
                self.graph.update(fdata)
            except Exception as e:
                print("Error processing frame:\n", e)
                traceback.print_exc()

            self.current_sweep_nr = f_current["frame_marker"] + 1
            self.current_frame_nr = frame_nr
            self.textboxes["label"].setText(label)
            self.labels["current_sweep"].setText(
                "Sweep: {} / {}".format(self.current_sweep_nr + 1, n_sweeps + 1)
            )
            self.labels["current_frame"].setText(
                "Frame: {} / {}".format(frame_nr + 1, total_frames + 1)
            )
            self.set_slider_value("sweep_slider", self.current_sweep_nr)
            return
        else:
            if record is None:
                print("No sweep data available")
                return
            label = self.textboxes["label"].text()

        sweep = number
        sweep = max(0, sweep)
        sweep = int(min(n_sweeps, sweep))

        frame_start = sweep - 1

        if self.feature_process is None:
            self.feature_process = feature_proc.FeatureProcessing(fdata["sensor_config"])

        self.feature_process.set_feature_list(fdata["ml_frame_data"]["feature_list"])

        try:
            fdata = self.feature_process.feature_extraction_window(
                fdata,
                record,
                frame_start,
                label
            )
        except Exception as e:
            self.gui_handle.error_message("Failed to calculate new feature frame<br>{}".format(e))

        self.current_sweep_nr = sweep

        if init:
            self.graph.reset_data()
        self.graph.update(fdata)

        self.current_frame_data = fdata["ml_frame_data"]["current_frame"]

        return

    def increment(self):
        self.num += 1
        return self.num

    def update_frame_data(self):
        action = self.sender().text()
        if self.gui_handle.ml_data is None:
            print("No feature data available")
            return
        if self.current_frame_data is None:
            print("Feature data not updated")
            return

        try:
            fdata = self.gui_handle.ml_data
            f_histdata = fdata["ml_frame_data"]["frame_list"]
            f_modified = self.current_frame_data
        except Exception as e:
            print("Something went wrong with the feature data: {}".format(e))
            return

        label = self.textboxes["label"].text()
        f_modified["label"] = label

        frame_nr = self.current_frame_nr

        if "new" in action:
            f_new = {}
            for key in f_histdata[frame_nr]:
                f_new[key] = f_modified[key]
            f_histdata.insert(frame_nr + 1, f_new)
            self.update_sliders()
            self.update_frame("frames", frame_nr + 2)
        elif "current" in action:
            for key in f_histdata[frame_nr]:
                f_histdata[frame_nr][key] = f_modified[key]
        elif "remove" in action:
            if len(f_histdata) > frame_nr:
                f_histdata.pop(frame_nr)
                self.update_frame("frames", frame_nr)
                self.update_sliders()

    def update_frame_labels(self):
        if self.gui_handle.ml_data is None:
            print("No feature data available")
            return
        if self.current_frame_data is None:
            print("Feature data not updated")
            return

        try:
            fdata = self.gui_handle.ml_data
            f_histdata = fdata["ml_frame_data"]["frame_list"]
            f_modified = self.current_frame_data
        except Exception as e:
            print("Something went wrong with the feature data: {}".format(e))
            return

        label = self.textboxes["label"].text()

        f_modified["label"] = label
        for frame in f_histdata:
            frame["label"] = label

    def update_sliders(self):
        if self.gui_handle.data is None or self.gui_handle.ml_data is None:
            return

        nr_sweeps = len(self.gui_handle.data.data)
        frame_size = self.gui_handle.ml_data["ml_frame_data"]["frame_info"]["frame_size"]
        nr_frames = len(self.gui_handle.ml_data["ml_frame_data"]["frame_list"])

        self.sliders["sweep_slider"].set_limits([1, max(nr_sweeps, 1) - (frame_size + 1)])
        self.sliders["frame_slider"].set_limits([1, max(nr_frames, 1)])

    def set_slider_value(self, tag, value):
        self.sliders[tag].set_value(value)

    def augment_data(self):
        fdata = self.gui_handle.ml_data
        if fdata is None:
            print("No feature data available!")
            return
        dialog = AugmentDataDialog(self)
        dialog.exec_()

        action, offsets = dialog.get_state()

        if action is None:
            return

        dialog.deleteLater()

        if not len(offsets):
            return
        else:
            try:
                offsets.sort()
            except Exception as e:
                print(e)
                return

        f_histdata = fdata["ml_frame_data"]["frame_list"]

        frame_nr = self.current_frame_nr

        f_info = fdata["ml_frame_data"]["frame_info"]

        record = self.gui_handle.data

        n_sweeps = len(record.data) - f_info["frame_size"] - 2 * f_info["frame_pad"]

        if frame_nr < 0:
            print("No feature data available!")
            return

        label = self.textboxes["label"].text()

        if self.feature_process is None:
            self.feature_process = feature_proc.FeatureProcessing(fdata["sensor_config"])

        self.feature_process.set_feature_list(fdata["ml_frame_data"]["feature_list"])

        if action == "all":
            frame_nr = 0
        sweep_nr = f_histdata[frame_nr]["frame_marker"]
        old_frame_nr = frame_nr

        while frame_nr >= 0:
            new_frame_nr = []
            count = 0
            for o in offsets:
                if o < 0:
                    new_frame_nr.append(frame_nr + count)
                    old_frame_nr += 1
                else:
                    new_frame_nr.append(frame_nr + count + 1)
                count += 1

            if new_frame_nr[0] < 0:
                zero = -new_frame_nr[0]
                for idx, val in enumerate(new_frame_nr):
                    new_frame_nr[idx] = val + zero

            errors = []
            added = 1
            for idx, o in enumerate(offsets):
                frame_start = sweep_nr + o
                if frame_start < 0:
                    print("Start sweep is less than 0 for offset {}!".format(o))
                elif frame_start > n_sweeps:
                    print("Start sweep is larger than total for offset {}!".format(o))
                else:
                    try:
                        fdata = self.feature_process.feature_extraction_window(
                            fdata,
                            record,
                            frame_start,
                            label
                        )
                    except Exception as e:
                        errors.append(e)
                    else:
                        f_new = {}
                        f_modified = fdata["ml_frame_data"]["current_frame"]
                        for key in f_modified:
                            f_new[key] = f_modified[key]
                        f_histdata.insert(new_frame_nr[idx], f_new)
                        added += 1
            if errors:
                self.gui_handle.error_message("Failed to calculate some feature frames")
            if action == "all":
                frame_nr += added
                if frame_nr >= len(f_histdata):
                    frame_nr = -1
                else:
                    sweep_nr = f_histdata[frame_nr]["frame_marker"]
            else:
                frame_nr = -1

        self.update_sliders()

        if action == "current":
            f = old_frame_nr
        else:
            f = 0
        self.gui_handle.feature_inspect.update_frame("frames", f + 1)


class LabelingGraph(QFrame):
    def __init__(self, parent, gui_handle=None):
        super().__init__(parent)

        featproc = feature_proc
        canvas = pg.GraphicsLayoutWidget()
        self.label_graph_widget = featproc.PGUpdater(info_text=False)
        self.label_graph_widget.setup(canvas)

        self.gui_handle = gui_handle
        self.grid = QtWidgets.QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)

        self.grid.addWidget(canvas, 0, 0)

    def update(self, plot_data):
        self.label_graph_widget.update(plot_data)

    def reset_data(self, sensor_config=None, processing_config=None):
        self.label_graph_widget.reset_data(
            sensor_config=sensor_config,
            processing_config=processing_config
        )


class TrainingFrame(QFrame):
    def __init__(self, parent, gui_handle=None):
        super().__init__(parent)

        self.grid = QtWidgets.QGridLayout()
        self.grid.setContentsMargins(9, 0, 9, 9)
        self.setLayout(self.grid)

        self.graph = TrainingGraph(self)

        self.color_table = []
        for i in range(101):
            rgb = colorsys.hsv_to_rgb(i / 300., 1.0, 1.0)
            self.color_table.append([round(255*x) for x in rgb])

        self.color_table_off = []
        for i in range(101):
            rgb = colorsys.hsv_to_rgb(1.0, i**2/100.0**2, 1.0)
            self.color_table_off.append([round(255*x) for x in rgb])

        self.labels = {
            "confusion_matrix": QLabel("Confusion Matrix"),
            "label_info": QLabel("Label info"),
        }

        self.labels["confusion_matrix"].setAlignment(QtCore.Qt.AlignHCenter)
        self.labels["label_info"].setAlignment(QtCore.Qt.AlignHCenter)

        self.cm_widget = QTableWidget()
        self.label_widget = QTableWidget()
        self.cm_widget.setMinimumWidth(700)
        self.grid.setColumnStretch(0, 1)

        self.num = 0
        self.grid.addWidget(self.graph, self.num, 0, 1, 2)
        self.grid.addWidget(QLabel(""), self.increment(), 0, 1, 2)
        self.grid.addWidget(self.labels["confusion_matrix"], self.increment(), 0)
        self.grid.addWidget(self.labels["label_info"], self.num, 1)
        self.grid.addWidget(self.cm_widget, self.increment(), 0)
        self.grid.addWidget(self.label_widget, self.num, 1)
        self.grid.setRowStretch(self.num, 1)

    def update_confusion_matrix(self, confusion_matrix):
        for r in range(self.cm_widget.rowCount()):
            for c in range(self.cm_widget.columnCount()):
                self.cm_widget.removeCellWidget(r, c)
        self.cm_widget.setRowCount(0)
        self.cm_widget.setColumnCount(0)

        if confusion_matrix is None:
            return

        try:
            labels = confusion_matrix["labels"]
            matrix = confusion_matrix["matrix"]
            row, col = matrix.shape
        except Exception as e:
            print(e)
            return

        self.cm_widget.setRowCount(row)
        self.cm_widget.setColumnCount(col)

        sum_correct = 0

        for r in range(row):
            row_sum = np.sum(matrix[r, :])
            for c in range(col):
                percent = matrix[r, c] / row_sum * 100
                if np.isnan(percent) or np.isinf(percent):
                    percent = 0
                    entry = "{} (N/A)".format(matrix[r, c])
                else:
                    entry = "{} ({:.2f}%)".format(matrix[r, c], percent)
                self.cm_widget.setItem(r, c, QTableWidgetItem(entry))
                self.cm_widget.item(r, c).setForeground(QBrush(QtCore.Qt.black))
                try:
                    int_percent = int(percent)
                except ValueError:
                    int_percent = 0
                color = self.color_table[int_percent]
                if r != c:
                    color = self.color_table_off[int_percent]
                else:
                    sum_correct += percent / col
                if "N/A" in entry:
                    color = self.color_table_off[0]
                self.cm_widget.item(r, c).setBackground(QColor(*color))
                self.cm_widget.item(r, c).setFlags(QtCore.Qt.ItemIsEnabled)

        print("Overall accuracy: {:.2f}".format(sum_correct))
        self.cm_widget.setHorizontalHeaderLabels(labels)
        self.cm_widget.setVerticalHeaderLabels(labels)

    def update_data_table(self, label_cat, label_list, loaded=False):
        for r in range(self.label_widget.rowCount()):
            for c in range(self.label_widget.columnCount()):
                self.label_widget.removeCellWidget(r, c)
        self.label_widget.setRowCount(0)
        self.label_widget.setColumnCount(0)

        if not loaded and label_cat is None:
            return

        if label_list is None:
            return

        try:
            if loaded and label_cat is None:
                label_nums = ["N/A"] * len(label_list)
            else:
                label_nums = [int(np.sum(label_cat[:, i])) for i in range(label_cat.shape[1])]
                if len(label_cat[0]) != len(label_list):
                    print("Error: Found {} categories, but {} labels!".format(
                        len(label_cat[0]), len(label_list))
                    )
                    return
            row = len(label_list)
            col = 1
        except Exception as e:
            print(e)
            return

        self.label_widget.setRowCount(row)
        self.label_widget.setColumnCount(1)

        for r in range(row):
            for c in range(col):
                entry = "{}".format(label_nums[r])
                self.label_widget.setItem(r, c, QTableWidgetItem(entry))
                self.label_widget.item(r, c).setForeground(QBrush(QtCore.Qt.black))
                self.label_widget.item(r, c).setFlags(QtCore.Qt.ItemIsEnabled)
        self.label_widget.setHorizontalHeaderLabels(["Number"])
        self.label_widget.setVerticalHeaderLabels(label_list)

    def show_results(self, plot_data=None, flush_data=False):
        self.graph.process(plot_data, flush_data)

    def increment(self):
        self.num += 1
        return self.num


class TrainingSidePanel(QFrame):
    sig_scan = pyqtSignal(str, str, object)

    def __init__(self, parent, gui_handle):
        super().__init__(parent)

        self.test_data = None
        self.eval_mode = None
        self.train_model_shape = None
        self.save_best_folder = None

        self.gui_handle = gui_handle
        self.ml_state = self.gui_handle.ml_state
        self.keras_handle = self.ml_state.keras_handle
        self.model_operation = self.gui_handle.ml_model_ops.model_operation

        self.grid = QtWidgets.QGridLayout()
        self.grid.setContentsMargins(9, 0, 9, 9)
        self.setLayout(self.grid)

        self.labels = {
            "model_header": QLabel("Load Training: "),
            "training": QLabel("Training Settings: "),
            "epochs": QLabel("Epochs: "),
            "batch_size": QLabel("Batch size:"),
            "optimizer": QLabel("Optimizer:"),
            "evaluate": QLabel("Validation settings: "),
            "learning_rate": QLabel("Learning rate:"),
            "delta": QLabel("Min. delta"),
            "patience": QLabel("Patience"),
            "train": QLabel("Train: "),
        }
        self.textboxes = {
            "epochs": QLineEdit("100"),
            "batch_size": QLineEdit("128"),
            "split": QLineEdit("0.2"),
            "learning_rate": QLineEdit("0.001"),
            "delta": QLineEdit("0.001"),
            "patience": QLineEdit("5"),
        }

        for tb in self.textboxes:
            self.textboxes[tb].editingFinished.connect(partial(self.check_vals, tb))

        for t in self.textboxes:
            self.textboxes[t].setStyleSheet("background-color: white")

        self.checkboxes = {
            "save_best": QCheckBox("Save best iteration"),
            "early_dropout": QCheckBox("Early dropout"),
        }
        self.checkboxes["early_dropout"].setChecked(True)
        self.checkboxes["save_best"].clicked.connect(self.save_best)

        self.buttons = {
            "train": QPushButton("Train"),
            "stop": QPushButton("Stop"),
            "validate": QPushButton("Validate"),
            "clear_weights": QPushButton("Clear weights"),
            "load_train_data": QPushButton("Load training data"),
            "load_test_data": QPushButton("Load test data"),
            "clear_training": QPushButton("Clear training/test data"),
        }

        self.buttons["train"].clicked.connect(partial(self.train, "train"))
        self.buttons["stop"].clicked.connect(partial(self.train, "stop"))
        self.buttons["load_train_data"].clicked.connect(self.load_train_data)
        self.buttons["load_test_data"].clicked.connect(self.load_train_data)
        self.buttons["clear_training"].clicked.connect(partial(self.model_operation, "clear_data"))
        self.buttons["validate"].clicked.connect(partial(self.model_operation, "validate_model"))
        self.buttons["clear_weights"].clicked.connect(
            partial(self.model_operation, "clear_weights")
        )

        self.buttons["stop"].setEnabled(False)
        self.buttons["train"].setEnabled(False)
        self.buttons["validate"].setEnabled(False)

        self.dropout_list = QComboBox()
        self.dropout_list.setMinimumHeight(25)
        self.dropout_list.addItem("Train Accuracy")
        self.dropout_list.addItem("Train Loss")
        self.dropout_list.addItem("Eval. Accuracy")
        self.dropout_list.addItem("Eval. Loss")
        self.dropout_list.setCurrentIndex(3)

        self.optimizer_list = QComboBox()
        self.optimizer_list.setMinimumHeight(25)
        self.optimizer_list.addItem("Adam")
        self.optimizer_list.addItem("Adagrad")
        self.optimizer_list.addItem("Adadelta")
        self.optimizer_list.addItem("RMSprop")
        self.optimizer_list.currentIndexChanged.connect(self.optimizer_learnining_rate)
        self.optimizer_list.setCurrentIndex(1)

        self.radiobuttons = {
            "split": QRadioButton("Split data"),
            "load": QRadioButton("Load test data"),
            "none": QRadioButton("No evaluation"),
        }

        self.radiobuttons["split"].setChecked(True)
        self.radio_frame = QFrame()
        self.radio_frame.grid = QtWidgets.QGridLayout(self.radio_frame)
        self.radio_frame.grid.setContentsMargins(0, 0, 0, 0)
        self.radio_frame.grid.addWidget(self.labels["evaluate"], 0, 0, 1, 2)
        self.radio_frame.grid.addWidget(QHLine(), 1, 0, 1, 2)
        self.radio_frame.grid.addWidget(self.radiobuttons["split"], 2, 0)
        self.radio_frame.grid.addWidget(self.textboxes["split"], 2, 1)
        self.radio_frame.grid.addWidget(self.radiobuttons["load"], 3, 0)
        self.radio_frame.grid.addWidget(self.buttons["load_test_data"], 3, 1)
        self.radio_frame.grid.addWidget(self.radiobuttons["none"], 4, 0)

        for toggle in self.radiobuttons:
            self.radiobuttons[toggle].toggled.connect(self.get_evaluation_mode)
        self.buttons["load_test_data"].setEnabled(False)

        self.num = -1
        self.grid.addWidget(QLabel(""), self.increment(), 0, 1, 4)
        self.grid.addWidget(self.labels["model_header"], self.increment(), 0, 1, 4)
        self.grid.addWidget(QHLine(), self.increment(), 0, 1, 4)
        self.grid.addWidget(self.buttons["load_train_data"], self.increment(), 0, 1, 2)
        self.grid.addWidget(self.buttons["clear_training"], self.num, 2, 1, 2)
        self.grid.addWidget(self.buttons["train"], self.increment(), 0, 1, 2)
        self.grid.addWidget(self.buttons["stop"], self.num, 2, 1, 2)
        self.grid.addWidget(self.buttons["validate"], self.increment(), 0, 1, 2)
        self.grid.addWidget(self.buttons["clear_weights"], self.num, 2, 1, 2)
        self.grid.addWidget(QLabel(""), self.increment(), 0, 1, 4)
        self.grid.addWidget(self.labels["training"], self.increment(), 0, 1, 4)
        self.grid.addWidget(QHLine(), self.increment(), 0, 1, 4)
        self.grid.addWidget(self.labels["epochs"], self.increment(), 0, 1, 2)
        self.grid.addWidget(self.textboxes["epochs"], self.num, 2, 1, 2)
        self.grid.addWidget(self.labels["batch_size"], self.increment(), 0, 1, 2)
        self.grid.addWidget(self.textboxes["batch_size"], self.num, 2, 1, 2)
        self.grid.addWidget(self.labels["optimizer"], self.increment(), 0, 1, 2)
        self.grid.addWidget(self.optimizer_list, self.num, 2, 1, 2)
        self.grid.addWidget(self.labels["learning_rate"], self.increment(), 0, 1, 2)
        self.grid.addWidget(self.textboxes["learning_rate"], self.num, 2, 1, 2)
        self.grid.addWidget(self.checkboxes["early_dropout"], self.increment(), 0, 1, 2)
        self.grid.addWidget(self.dropout_list, self.num, 2, 1, 2)
        self.grid.addWidget(self.labels["patience"], self.increment(), 0)
        self.grid.addWidget(self.textboxes["patience"], self.num, 1)
        self.grid.addWidget(self.labels["delta"], self.num, 2)
        self.grid.addWidget(self.textboxes["delta"], self.num, 3)
        self.grid.addWidget(self.checkboxes["save_best"], self.increment(), 0, 1, 2)
        self.grid.addWidget(QLabel(""), self.increment(), 0, 1, 4)
        self.grid.addWidget(self.radio_frame, self.increment(), 0, 1, 4)
        self.grid.addWidget(QLabel(""), self.increment(), 0, 1, 4)

        self.grid.setRowStretch(self.increment(), 1)

    def increment(self):
        self.num += 1
        return self.num

    def load_train_data(self):
        mode = "training"
        if "test" in self.sender().text():
            mode = "test"
        title = "Load and extract {} data".format(mode)

        options = QtWidgets.QFileDialog.Options()
        options |= QtWidgets.QFileDialog.DontUseNativeDialog
        filenames, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, title, "", "NumPy data files (*.npy)", options=options)

        model_exists = self.ml_state.get_model_status()
        layer_list = self.gui_handle.model_select.get_layer_list()

        if filenames:
            try:
                if mode == "training":
                    data = self.keras_handle.load_train_data(
                        filenames,
                        layer_list=layer_list,
                        model_exists=model_exists,
                    )
                else:
                    data = self.keras_handle.load_test_data(filenames)
            except Exception as e:
                self.gui_handle.error_message("Failed to load {} data:\n {}".format(mode, e))
                return

            status = data["info"]

            if status["success"]:
                # Update sensor settings from training data
                if model_exists:
                    s = self.ml_state.get_model_source()
                else:
                    s = "internal"
                self.ml_state.set_model_data(data["model_data"], source=s)
                self.gui_handle.ml_model_ops.config_is_valid(show_warning=False)
                conf = self.gui_handle.get_sensor_config()
                model_conf_dump = data["model_data"]["sensor_config"]._dumps()
                conf._loads(model_conf_dump)
                self.gui_handle.set_sensors(data["model_data"]["sensor_config"].sensor)

                if mode == "training":
                    self.ml_state.set_training_data_status(True, filenames)
                    self.gui_handle.training.update_data_table(
                        data["model_data"]["y_labels"],
                        data["model_data"]["label_list"]
                    )
                else:
                    self.ml_state.set_test_data_status(True, filenames)

                self.gui_handle.model_select.allow_update(status["success"])
                if status["model_initialized"]:
                    self.buttons["train"].setEnabled(True)
                    self.gui_handle.info_handle(status["message"])
                    self.gui_handle.model_select.set_layer_shapes(
                        data["model_data"]["keras_layer_info"]
                    )
                    self.gui_handle.model_select.dump_layers(
                        data["model_data"]["layer_list"],
                        "last_model.yaml"
                    )
                    self.buttons["validate"].setEnabled(True)
                    if not model_exists:
                        self.gui_handle.feature_select.update_feature_list(
                            data["model_data"]["feature_list"]
                        )
                else:
                    message = status["message"] + status["model_status"]
                    self.gui_handle.error_message(message)
            else:
                self.gui_handle.error_message(status["message"])
                self.model_operation("clear_data")
                return

            if mode == "training":
                self.gui_handle.training.show_results(flush_data=True)

    def get_evaluation_mode(self):
        eval_data = None
        if self.radiobuttons["split"].isChecked():
            self.buttons["load_test_data"].setEnabled(False)
            self.textboxes["split"].setEnabled(True)
            try:
                eval_data = float(self.textboxes["split"].text())
            except Exception:
                eval_data = 0.2
                self.textboxes["split"] = 0.2
            if eval_data <= 0 or eval_data > 0.9:
                eval_data = 0.2
                self.textboxes["split"] = 0.2
        if self.radiobuttons["load"].isChecked():
            self.buttons["load_test_data"].setEnabled(True)
            self.textboxes["split"].setEnabled(False)
            if self.test_data is not None:
                try:
                    eval_data = (self.test_data["x_data"], self.test_data["y_labels"])
                except Exception as e:
                    print("Failed to use loaded data for evaluation.\n", e)
        if self.radiobuttons["none"].isChecked():
            self.buttons["load_test_data"].setEnabled(False)
            self.textboxes["split"].setEnabled(False)
        return eval_data

    def get_learning_rate(self):
        rate = float(self.textboxes["learning_rate"].text())
        return rate

    def get_optimizer(self):
        return self.optimizer_list.currentText()

    def optimizer_learnining_rate(self):
        opt = self.optimizer_list.currentText()
        if opt == "Adam":
            self.textboxes["learning_rate"].setText("0.001")
        elif opt == "Adagrad":
            self.textboxes["learning_rate"].setText("0.01")
        elif opt == "Adadelta":
            self.textboxes["learning_rate"].setText("1.0")
        elif opt == "RMSprop":
            self.textboxes["learning_rate"].setText("0.001")

    def get_dropout(self):
        if not self.checkboxes["early_dropout"].isChecked():
            return False

        dropout = self.dropout_list.currentText()
        if dropout == "Train Accuracy":
            dropout = "acc"
        elif dropout == "Train Loss":
            dropout = "loss"
        elif dropout == "Eval. Accuracy":
            dropout = "val_acc"
        elif dropout == "Eval. Loss":
            dropout = "val_loss"
        else:
            print("Unknown dropout condition! ", dropout)
            dropout = False

        patience = int(self.textboxes["patience"].text())
        delta = float(self.textboxes["delta"].text())

        return {"monitor": dropout, "patience": patience, "min_delta": delta}

    def save_best(self):
        enabled = self.sender().isChecked()
        if enabled:
            title = "Select folder to save best iteration"
            options = QtWidgets.QFileDialog.Options()
            options |= QtWidgets.QFileDialog.DontUseNativeDialog

            folder = QtWidgets.QFileDialog.getExistingDirectory(
                self, title, options=options)

            if folder:
                self.save_best_folder = folder
            else:
                self.save_best_folder = None
                self.sender().setCheck(False)
        else:
            self.save_best_folder = None

    def train(self, mode):
        if mode == "stop":
            try:
                self.sig_scan.emit("stop", "", "")
            except Exception:
                pass
            self.buttons["stop"].setEnabled(False)
            self.buttons["train"].setEnabled(True)
            self.buttons["validate"].setEnabled(True)
            return

        model_data = self.ml_state.get_model_data()
        if model_data["loaded"] is False:
            self.gui_handle.error_message("Model not ready")
            return
        if self.ml_state.get_training_data_status() is False:
            self.gui_handle.error_message("No training data loaded")
            return

        # Make sure correct layer list is displayed
        self.gui_handle.model_select.update_layer_list(model_data["layer_list"])
        self.gui_handle.model_select.allow_update(False)
        self.gui_handle.tab_parent.setCurrentIndex(TRAIN_TAB)

        ep = int(self.textboxes["epochs"].text())
        batch = int(self.textboxes["batch_size"].text())
        func = self.gui_handle.training.show_results

        self.buttons["stop"].setEnabled(True)
        self.buttons["train"].setEnabled(False)
        self.buttons["validate"].setEnabled(False)

        if self.save_best_folder is not None:
            save_best_info = {
                "folder": self.save_best_folder,
                "feature_list": model_data["feature_list"],
                "frame_settings": model_data["frame_settings"],
                "sensor_config": model_data["sensor_config"],
            }
        else:
            save_best_info = None

        # Todo: Finalize threaded training
        thread_training = True
        model_params = {
            "epochs": ep,
            "batch_size": batch,
            "eval_data": self.get_evaluation_mode(),
            "save_best": save_best_info,
            "dropout": self.get_dropout(),
            "session": self.keras_handle.get_current_session(),
            "graph": self.keras_handle.get_current_graph(),
            "learning_rate": self.get_learning_rate(),
            "optimizer": self.get_optimizer(),
            "plot_cb": func,
        }

        if thread_training:
            model_params["model"] = self.keras_handle
            self.threaded_train = Threaded_Training(model_params, parent=self)
            self.threaded_train.sig_scan.connect(self.thread_receive)
            self.sig_scan.connect(self.threaded_train.receive)
            self.threaded_train.start()
        else:
            self.is_training(True)
            self.train_history = self.keras_handle.train(model_params)
            self.is_training(False)
            self.buttons["stop"].setEnabled(False)
            self.buttons["train"].setEnabled(True)
            self.buttons["validate"].setEnabled(True)
            self.gui_handle.ml_model_ops.generate_confusion_matrix(model_data["y_labels"])

        try:
            self.gui_handle.load_gui_settings_from_sensor_config(model_data["sensor_config"])
            self.gui_handle.set_sensors(model_data["sensor_config"].sensor)
            self.gui_handle.feature_select.update_feature_list(model_data["feature_list"])
            self.gui_handle.feature_sidepanel.set_frame_settings(model_data["frame_settings"])
        except Exception as e:
            print(e)

    def thread_receive(self, message_type, message, data=None):
        if "training_error" in message_type:
            self.gui_handle.error_message(("{}".format(message)))
            self.buttons["stop"].setEnabled(False)
            self.buttons["train"].setEnabled(True)
        elif message_type == "training_done":
            model_data = self.ml_state.get_model_data()
            self.keras_handle.set_current_session(data[2])
            self.buttons["stop"].setEnabled(False)
            self.buttons["train"].setEnabled(True)
            self.buttons["validate"].setEnabled(True)
            self.gui_handle.ml_model_ops.generate_confusion_matrix(model_data["y_labels"])
        elif message_type == "update_plots":
            self.gui_handle.training.show_results(data)
        else:
            print("Thread data not implemented! {}".format(message_type))
            print(message_type, message, data)

    def check_vals(self, box):
        success = True
        val = -1
        if box in ["learning_rate", "split", "delta"]:
            try:
                val = float(self.sender().text())
            except Exception:
                pass
            if val <= 0 or val >= 10:
                if box in ["learning_rate", "delta"]:
                    val = "0.001"
                if box == "split":
                    val = "0.2"
                success = False
        if box in ["epochs", "batch_size", "patience"]:
            try:
                val = int(self.sender().text())
            except Exception:
                pass
            if val < 1:
                if box == "epochs":
                    val = "100"
                if box == "batch_size":
                    val = "128"
                if box == "patience":
                    val = "5"
                success = False

        if not success:
            self.sender().setText(val)

    def is_training(self, val):
        if val:
            self.gui_handle.enable_tabs(False)
        else:
            self.gui_handle.enable_tabs(True)


class TrainingGraph(QFrame):
    def __init__(self, parent, gui_handle=None):
        super().__init__(parent)

        canvas = pg.GraphicsLayoutWidget()
        self.training_graph_widget = kp.KerasPlotting()
        self.training_graph_widget.setup(canvas)

        self.gui_handle = gui_handle
        self.grid = QtWidgets.QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)

        self.grid.addWidget(canvas, 0, 0)

    def update(self, plot_data):
        self.training_graph_widget.update(plot_data)

    def process(self, plot_data, flush_data):
        self.training_graph_widget.process(data=plot_data, flush_data=flush_data)
        QApplication.processEvents()


class ModelSelectFrame(QFrame):
    def __init__(self, parent, gui_handle=None):
        super().__init__(parent)
        self.param_col = 2
        self.remove_col = self.param_col + 2
        self.nr_col = self.remove_col + 1
        self.row_idx = Count(2)
        self.gui_handle = gui_handle
        self.ml_state = gui_handle.ml_state
        self.keras_handle = self.ml_state.keras_handle

        self._grid = QtWidgets.QGridLayout()
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(0)
        self.setLayout(self._grid)

        self.model_frame_scroll = QtWidgets.QScrollArea()
        self.model_frame_scroll.setFrameShape(QFrame.NoFrame)
        self.model_frame_scroll.setWidgetResizable(True)
        self.model_frame_scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.model_frame_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)

        self.model_frame = QFrame(self.model_frame_scroll)
        self.model_frame_scroll.setWidget(self.model_frame)

        self._grid.addWidget(self.model_frame_scroll)
        self._layout = QtWidgets.QGridLayout()
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._layout.setAlignment(QtCore.Qt.AlignCenter)
        self.model_frame.setLayout(self._layout)

        self.enabled_layers = []
        self.layers = layer_def.get_layers()

        self.enabled_count = Count()
        self.create_grid()
        self.parse_layers()
        self.update_grid()

        self.layer_drop_down.setCurrentIndex(0)
        self._grid.addWidget(self.bottom_widget, 1, 0)

    def create_grid(self):
        self.labels = {
            "error_text": QLabel(""),
            "layer_header": QLabel("Layer"),
            "param_header": QLabel("Parameters"),
        }
        self.labels["error_text"].setStyleSheet("QLabel {color: red}")

        self._layout.addWidget(self.labels["layer_header"], 0, 0)
        self._layout.addWidget(self.labels["param_header"], 0, self.param_col)
        self._layout.addWidget(QHLine(), 1, 0, 1, self.nr_col)
        self.name_vline = QVLine()
        self.params_vline = QVLine()
        self.remove_vline = QVLine()

        self.buttons = {
            "update": QPushButton("Update model"),
            "reset": QPushButton("Reset layers"),
            "load": QPushButton("Load layers"),
            "save": QPushButton("Save layers"),
        }
        self.buttons["update"].setEnabled(False)

        self.layer_drop_down = QComboBox()
        self.layer_drop_down.addItem("Add layer")

        self.bottom_widget = QWidget()
        bottom = QVBoxLayout()
        bottom.setContentsMargins(2, 2, 2, 2)
        bottom.setSpacing(2)
        self.bottom_widget.setLayout(bottom)
        bottom_first = QWidget()
        first = QHBoxLayout()
        first.setContentsMargins(2, 2, 2, 2)
        first.setSpacing(2)
        first.setAlignment(QtCore.Qt.AlignLeft)
        bottom_first.setLayout(first)
        first.addWidget(self.layer_drop_down)
        first.addWidget(self.buttons["update"])
        first.addWidget(self.buttons["reset"])
        first.addWidget(self.buttons["load"])
        first.addWidget(self.buttons["save"])
        first.addStretch(2)
        first.addWidget(self.labels["error_text"])
        bottom_second = QWidget()
        second = QHBoxLayout()
        second.setContentsMargins(2, 2, 2, 2)
        second.setSpacing(2)
        second.setAlignment(QtCore.Qt.AlignLeft)
        bottom_second.setLayout(second)
        self.model_variables = {
            "trainable": QLabel(""),
            "non_trainable": QLabel(""),
            "total": QLabel(""),
        }
        for l in self.model_variables:
            second.addWidget(self.model_variables[l])

        bottom.addWidget(bottom_first)
        bottom.addWidget(bottom_second)

        for b in self.buttons:
            button = self.buttons[b]
            button.clicked.connect(self.model_actions)

    def model_actions(self):
        action = self.sender().text()
        if action == "Reset layers":
            if os.path.isfile("last_model.yaml"):
                f = "last_model.yaml"
            else:
                f = DEFAULT_MODEL_FILENAME_2D
            self.load_layers(f)
            self.ml_state.set_state("layers_changed", True)
        elif action == "Update model":
            model_ready = self.ml_state.get_model_status()
            training_ready = self.ml_state.get_training_data_status()
            if not model_ready and not training_ready:
                self.gui_handle.model_select.allow_update(False)
                self.gui_handle.error_message("Load model or training data first!")
            else:
                layer_list = self.get_layer_list()
                status = self.keras_handle.update_model_layers(layer_list)
                if status["info"]["model_initialized"]:
                    self.set_layer_shapes(status["model_data"]["keras_layer_info"])
                    s = self.ml_state.get_model_source()
                    self.ml_state.set_model_data(status["model_data"], source=s)
                    self.allow_update(False)
                else:
                    self.ml_state.set_model_data(None)
                    self.gui_handle.error_message(status["info"]["model_message"])
                    self.allow_update(True)
        else:
            title = "Save/Load layer settings"
            options = QtWidgets.QFileDialog.Options()
            options |= QtWidgets.QFileDialog.DontUseNativeDialog
            file_types = "YAML layer data files (*.yaml)"

            if action == "Save layers":
                filename, info = QtWidgets.QFileDialog.getSaveFileName(
                    self, title, "", file_types, options=options)
            elif action == "Load layers":
                filename, info = QtWidgets.QFileDialog.getOpenFileName(
                    self, title, "", file_types, options=options)

            if not filename:
                return

            if action == "Load layers":
                self.load_layers(filename)
            elif action == "Save layers":
                if os.path.splitext(filename)[1] != ".yaml":
                    os.path.join(filename, ".yaml")
                self.dump_layers(self.get_layer_list(include_inactive_layers=True), filename)

    def dump_layers(self, layers, filename):
        try:
            with open(filename, 'w') as f_handle:
                yaml.dump(layers, f_handle, default_flow_style=False)
        except Exception as e:
            print("Failed to dump layers to file {}!\n".format(filename), e)

    def load_layers(self, filename):
        try:
            with open(filename, 'r') as f_handle:
                layers = yaml.full_load(f_handle)
            self.update_layer_list(layers)
        except Exception as e:
            print("Failed to load layers\n", e)
        return layers

    def allow_layer_edit(self, allow):
        self.model_frame.setEnabled(allow)
        self.bottom_widget.setEnabled(allow)

        if allow:
            self.labels["error_text"].setText("")
        else:
            self.labels["error_text"].setText("Cannot edit layers for models loaded from file!")

    def update_grid(self):
        try:
            self._layout.removeWidget(self.name_vline)
            self._layout.removeWidget(self.params_vline)
            self._layout.removeWidget(self.remove_vline)
        except Exception:
            pass

        for i in range(self.row_idx.val):
            self._layout.setRowStretch(i, 0)

        layer_nr = 1
        for idx, l in enumerate(self.enabled_layers):
            l["layer_control"].update_value(idx + 1)
            if l["is_active"]:
                l["other_items"][1].setText("Layer {}".format(layer_nr))
                layer_nr += 1
            else:
                l["other_items"][1].setText("Layer inactive")

        self._layout.addWidget(self.name_vline, 0, 1, self.row_idx.val + 1, 1)
        self._layout.addWidget(self.params_vline, 0, self.param_col + 1, self.row_idx.val + 1, 1)
        self._layout.addWidget(self.remove_vline, 0, self.remove_col + 1, self.row_idx.val + 1, 1)

        self.layer_drop_down.setCurrentIndex(0)

        self._layout.setRowStretch(self.row_idx.val + 2, 1)
        self._layout.setColumnStretch(3, 1)
        self._layout.setColumnStretch(self.nr_col, 1)

    def increment(self, skip=[1]):
        self.num += 1
        self.increment_skip(skip)
        return self.num

    def parse_layers(self):
        self.layer_list = {}
        self.name_to_key = {}

        for key in self.layers:
            try:
                layer = self.layers[key]
                name = layer["class_str"]
                self.layer_list[key] = {
                    "name": name,
                    "params": layer["params"],
                    "dimensions": layer["dimensions"],
                }
                self.name_to_key[name] = key
            except Exception as e:
                print("Failed to add layer!\n", e)

        for key in self.layer_list:
            self.layer_drop_down.addItem(self.layer_list[key]["name"])

        self.layer_drop_down.currentIndexChanged.connect(self.add_layer_details)

    def add_layer_details(self, data, key=None):
        if not key:
            index = self.sender().currentIndex()
            if index == 0:
                return
            else:
                try:
                    key = self.name_to_key[self.sender().currentText()]
                except KeyError:
                    print("Unknown feature: {}\n".format(self.sender().currentText()))
                    return
                except Exception as e:
                    print("Something went wrong!\n", e)
                    return

        self._layout.removeWidget(self.bottom_widget)

        layer = self.layers[key]
        dimensions = layer["dimensions"]
        layer_params = layer["params"]
        self.num = 0
        row = self.row_idx.pre_incr()

        other_items = []
        other_items.append(QLabel(key))
        self._layout.addWidget(other_items[0], row, self.num)

        params_widget = QWidget(self)
        params_box = QHBoxLayout()
        params_box.setAlignment(QtCore.Qt.AlignLeft)
        params_widget.setLayout(params_box)
        self._layout.addWidget(params_widget, row, self.param_col)
        params = {}
        labels = {}
        if layer_params is not None:
            for text in layer_params:
                p = layer_params[text]
                labels[text] = QLabel(text)
                params_box.addWidget(labels[text])
                if p[0] == "drop_down":
                    limits = data_type = value = None
                    params[text] = QComboBox(self)
                    for item in p[1]:
                        params[text].addItem(item)
                    if "conv" in key.lower():
                        params[text].setCurrentIndex(1)
                    else:
                        params[text].setCurrentIndex(2)
                    edit = params[text].currentIndexChanged
                else:
                    value, data_type, limits = p
                    if data_type == bool:
                        params[text] = QCheckBox(self)
                        params[text].setChecked(value)
                        edit = params[text].stateChanged
                    else:
                        box = []
                        edit = []
                        if isinstance(value, tuple):
                            box.append(QLabel("("))
                            for index, v in enumerate(value):
                                box.append(QLineEdit(str(v)))
                                if index < len(value) - 1:
                                    box.append(QLabel("x"))
                            box.append(QLabel(")"))
                        else:
                            box.append(QLineEdit(str(value)))
                        params[text] = box
                        for entry in box:
                            if isinstance(entry, QtWidgets.QLineEdit):
                                edit.append(entry.editingFinished)
                                entry.setMaximumWidth(40)

                if not isinstance(edit, list):
                    edit = [edit]
                if not isinstance(params[text], list):
                    params[text] = [params[text]]

                for entry in edit:
                    entry.connect(
                        partial(self.update_layer_params, limits, data_type, value)
                    )

                for entry in params[text]:
                    entry.setFixedHeight(25)
                    params_box.addWidget(entry)
                params_box.addStretch(1)
        else:
            params = None
            place_holder = QLabel("")
            place_holder.setFixedHeight(25)
            params_box.addWidget(place_holder)
        params_box.addStretch(100)

        layer_output_shape = QLabel("")
        self._layout.addWidget(layer_output_shape, row + 1, self.param_col)

        layer_position = len(self.enabled_layers) + 1
        layer_control = ModelLayerSpinBox(layer_position, self, callback=self.update_layer)
        self._layout.addWidget(layer_control, row, self.remove_col, 2, 1)

        row = self.row_idx.pre_incr()

        other_items.append(QLabel("Layer {}".format(len(self.enabled_layers) + 1)))
        self._layout.addWidget(other_items[1], row, 0)

        other_items.append(QHLine())

        self._layout.addWidget(other_items[2], self.row_idx.pre_incr(), 0, 1, self.nr_col)

        layer_params = {
            "key": key,
            "name": self.layer_list[key]["name"],
            "params": params,
            "labels": labels,
            "other_items": other_items,
            "layer_control": layer_control,
            "count": self.enabled_count.val,
            "dimensions": dimensions,
            "layer_output_shape": layer_output_shape,
            "params_box": params_box,
            "params_widget": params_widget,
            "is_active": True,
        }

        self.enabled_layers.append(layer_params)

        self.update_grid()

    def update_layer(self, action=None, layer_position=None, value=None):
        if action == "remove_layer":
            self.remove_layer(pos=layer_position)
        if action == "is_active":
            layer = self.enabled_layers[layer_position-1]
            layer["is_active"] = value
            layer["params_widget"].setEnabled(value)
            for w in layer["other_items"]:
                w.setEnabled(value)
            self.update_grid()
        if action == "move_layer":
            self.move_layer(layer_position - 1, value - 1)

        self.ml_state.set_state("layers_changed", True)
        self.allow_update(allow=True, set_red=True)

        self.set_layer_shapes(None)

    def allow_update(self, allow=None, set_red=False):
        # Sanity check status
        training_ready = self.ml_state.get_training_data_status()
        if allow and not training_ready:
            allow = False

        if allow is not None:
            self.buttons["update"].setEnabled(allow)

        if set_red and allow:
            c = "red"
        elif allow:
            c = "black"
        else:
            c = "grey"

        if c == "red":
            self.labels["error_text"].setText("Layers edited, update model to apply changes!")
        else:
            self.labels["error_text"].setText("")

        self.buttons["update"].setStyleSheet("QPushButton {{color: {}}}".format(c))

    def move_layer(self, layer_pos, move_to):
        out_of_limits = False
        insert_pos = []
        to_pos = 0

        touch_layers = [layer_pos, move_to]

        if move_to >= len(self.enabled_layers) or move_to < 0:
            out_of_limits = True

        for idx, layer in enumerate(self.enabled_layers):
            if out_of_limits or idx not in touch_layers:
                continue

            widgets = []
            widgets.append(layer["layer_control"])
            widgets.append(layer["params_widget"])
            widgets.append(layer["layer_output_shape"])

            for i in layer["other_items"]:
                widgets.append(i)

            if idx == layer_pos:
                for w in widgets:
                    i = self._layout.indexOf(w)
                    pos = self._layout.getItemPosition(i)
                    insert_pos.append(pos)
                    self._layout.removeWidget(w)
                reinsert = widgets
            else:
                if move_to < layer_pos:
                    shift_index = 3
                else:
                    shift_index = -3

                if idx == move_to:
                    i = self._layout.indexOf(widgets[0])
                    pos = self._layout.getItemPosition(i)
                    to_pos = pos[0]

                for w in widgets:
                    i = self._layout.indexOf(w)
                    pos = self._layout.getItemPosition(i)
                    self._layout.removeWidget(w)
                    self._layout.addWidget(w, pos[0] + shift_index, pos[1], pos[2], pos[3])

        if not out_of_limits:
            shift_index = to_pos - insert_pos[0][0]
            for w, pos in zip(reinsert, insert_pos):
                self._layout.addWidget(w, pos[0] + shift_index, pos[1], pos[2], pos[3])

            self.enabled_layers.insert(move_to, self.enabled_layers.pop(layer_pos))

        self.update_grid()

    def remove_layer(self, pos=None, clear_all=False):
        if not clear_all:
            if pos is None:
                button = self.sender()
                button_idx = self._layout.indexOf(button)
                pos = self._layout.getItemPosition(button_idx)
                list_pos = [int((pos[0] - 2) / 3)]
            else:
                list_pos = [pos-1]
        else:
            list_pos = list(range(len(self.enabled_layers)))

        pop_list = []
        for lpos in list_pos:
            for idx, layer in enumerate(self.enabled_layers):

                if idx < lpos:
                    continue

                widgets = []
                widgets.append(layer["layer_control"])
                widgets.append(layer["params_widget"])
                widgets.append(layer["layer_output_shape"])

                for i in layer["other_items"]:
                    widgets.append(i)

                if idx == lpos:
                    for w in widgets:
                        self._layout.removeWidget(w)
                        w.deleteLater()
                        w = None
                else:
                    for w in widgets:
                        idx = self._layout.indexOf(w)
                        pos = self._layout.getItemPosition(idx)
                        self._layout.removeWidget(w)
                        self._layout.addWidget(w, pos[0] - 3, pos[1], pos[2], pos[3])

            pop_list.append(lpos)
            self.row_idx.decr(val=3)
            if len(pop_list) == len(self.enabled_layers):
                self.row_idx.set_val(1)

        pop_list.sort(reverse=True)
        for i in pop_list:
            self.enabled_layers.pop(i)

        self.update_grid()

    def get_layer_list(self, enabled_layers=None, include_inactive_layers=False):
        l_list = []

        if enabled_layers is None:
            enabled_layers = self.enabled_layers
        if not isinstance(enabled_layers, list):
            enabled_layers = [enabled_layers]

        for idx, layer in enumerate(enabled_layers):
            if not layer["is_active"] and not include_inactive_layers:
                continue
            key = layer["key"]
            list_entry = {
                "name": key,
                "class": layer["name"],
                "params": {},
                "is_active": layer["is_active"],
            }
            if layer["params"] is not None:
                for opt in layer["params"]:
                    param_list = []
                    for p in layer["params"][opt]:
                        if isinstance(p, QtWidgets.QCheckBox):
                            param_list.append(p.isChecked())
                        elif isinstance(p, QtWidgets.QComboBox):
                            param_list.append(p.currentText())
                        elif isinstance(p, QLineEdit):
                            convert_cb = self.layers[key]['params'][opt][1]
                            param_list.append(convert_cb(p.text()))
                    if len(param_list) > 1:
                        list_entry["params"][opt] = param_list
                    else:
                        list_entry["params"][opt] = param_list[0]
            else:
                list_entry["params"] = None

            l_list.append(list_entry)

        return l_list

    def update_layer_list(self, saved_layer_list):
        # check if layer list is valid
        if saved_layer_list is None:
            return
        try:
            for saved in saved_layer_list:
                layer = {}
                layer["name"] = saved["name"]
                layer["class"] = saved["class"]
        except Exception as e:
            print("Layer list not compatible!\n", e)
            return

        self.remove_layer(clear_all=True)

        error_message = "Feature Classes not found:\n"
        all_found = True
        for s_layer in saved_layer_list:
            try:
                layer_key = s_layer["name"]
                self.add_layer_details(None, key=layer_key)
            except Exception:
                error_message += ("Feature Name: {}\n".format(s_layer["name"]))
                all_found = False
            else:
                if layer_key in self.layer_list:
                    e_layer = self.enabled_layers[-1]
                else:
                    print("Unknown layer key {}". format(layer_key))
                    continue

                is_active = s_layer.get("is_active", True)
                if not is_active:
                    e_layer["layer_control"].set_active(False)

                if s_layer["params"] is None:
                    continue

                for p in s_layer["params"]:
                    saved_value = s_layer["params"][p]
                    boxes = e_layer["params"][p]
                    for box in boxes:
                        if isinstance(box, QtWidgets.QCheckBox):
                            box.setChecked(saved_value[0])
                        elif isinstance(box, QtWidgets.QComboBox):
                            index = box.findText(saved_value, QtCore.Qt.MatchFixedString)
                            if index >= 0:
                                box.setCurrentIndex(index)
                        elif isinstance(box, QtWidgets.QLineEdit):
                            added = 0
                            if isinstance(saved_value, list):
                                box.setText(str(saved_value[added]))
                                added += 1
                            else:
                                box.setText(str(saved_value))

        if not all_found:
            try:
                self.gui_handle.error_message(error_message)
            except Exception:
                print(error_message)
        QApplication.processEvents()

        return all_found

    def set_layer_shapes(self, keras_layer_list):
        if keras_layer_list is None:
            for layer in self.enabled_layers:
                layer["layer_output_shape"].setText("")
            for key in self.model_variables:
                self.model_variables[key].setText("")
        else:
            active_layers = []
            for i, l in enumerate(self.enabled_layers):
                if l["is_active"]:
                    active_layers.append(i)
            for idx, layer in enumerate(keras_layer_list):
                if idx == 0:
                    continue
                out = "Output: {}".format(layer.output_shape)
                self.enabled_layers[active_layers[idx-1]]["layer_output_shape"].setText(out)
            try:
                variables = self.keras_handle.count_variables()
                if variables is not None:
                    total = 0
                    for key in variables:
                        text = "{}: {}".format(key, variables[key])
                        total += variables[key]
                        self.model_variables[key].setText(text)
                    self.model_variables["total"].setText("Total: {}".format(total))
            except Exception as e:
                print("Failed to parse trainable variables!\n", e)

    def clearLayout(self):
        while self._layout.count():
            child = self._layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def update_layer_params(self, limits, data_type, default):
        self.ml_state.set_state("layers_changed", True)
        self.allow_update(allow=True, set_red=True)

        self.set_layer_shapes(None)
        return


class EvalFrame(QFrame):
    def __init__(self, parent, gui_handle=None):
        super().__init__(parent)

        self.feature_process = None
        self.gui_handle = gui_handle
        self.nr_col = 2

        self.grid = QtWidgets.QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)

        self.setLayout(self.grid)

    def init_graph(self):
        if self.gui_handle.current_module_label == "Select service":
            self.gui_handle.module_dd.setCurrentIndex(2)

        feature_canvas = pg.GraphicsLayoutWidget()
        self.plot_widget = feature_proc.PGUpdater(
            self.gui_handle.save_gui_settings_to_sensor_config(),
            self.gui_handle.update_service_params(),
            predictions=True
        )
        self.plot_widget.setup(feature_canvas)

        self.grid.addWidget(feature_canvas, 0, 0, 1, self.nr_col)


class ModelOperations(QFrame):
    def __init__(self, parent):
        super().__init__(parent)

        self.gui_handle = parent
        self.ml_state = self.gui_handle.ml_state
        self.keras_handle = self.ml_state.keras_handle

    def model_operation(self, op):
        model_ready = self.ml_state.get_model_status()
        training_ready = self.ml_state.get_training_data_status()
        training_buttons = self.gui_handle.training_sidepanel.buttons
        if op == "save_model":
            if not model_ready:
                print("No model data available")
                return
            title = "Save model and settings"
            options = QtWidgets.QFileDialog.Options()
            options |= QtWidgets.QFileDialog.DontUseNativeDialog

            file_types = "NumPy data files (*.npy)"
            fname = 'model_data_{date:%Y_%m_%d_%H%M}'.format(date=datetime.datetime.now())
            filename, info = QtWidgets.QFileDialog.getSaveFileName(
                self, title, fname, file_types, options=options)

            if filename:
                if not model_ready:
                    self.gui_handle.info_message("No model data available:\n")
                    return
                try:
                    model_data = self.ml_state.get_model_data()
                    self.keras_handle.save_model(
                        filename,
                        model_data["feature_list"],
                        model_data["sensor_config"],
                        model_data["frame_settings"],
                    )
                except Exception as e:
                    self.gui_handle.error_message("Failed to save model:\n {}".format(e))
                    return
        if op == "clear_weights":
            if model_ready:
                self.keras_handle.clear_model(reinit=True)
            self.gui_handle.training.show_results(flush_data=True)
            self.gui_handle.training.update_confusion_matrix(None)

        elif op == "clear_data" or op == "remove_model":
            if model_ready:
                if op == "clear_data":
                    self.keras_handle.clear_training_data()
                    self.gui_handle.model_select.allow_update(False)
                else:
                    self.gui_handle.model_select.allow_update(
                        self.ml_state.get_training_data_status()
                    )
                self.ml_state.set_model_data(None)
            self.gui_handle.training.show_results(flush_data=True)
            self.gui_handle.training.update_data_table(None, None)
            self.gui_handle.training.update_confusion_matrix(None)
            self.gui_handle.model_select.set_layer_shapes(None)

            if op == "clear_data":
                self.ml_state.set_training_data_status(False)
                self.ml_state.set_test_data_status(False)

        elif op == "load_model":
            self.load_model()

        elif op == "validate_model":
            if not training_ready:
                self.gui_handle.error_message("No training data loaded")
                training_buttons["validate"].setEnabled(False)
                return
            self.generate_confusion_matrix(self.ml_state.get_model_data()["y_labels"])
            self.gui_handle.tab_parent.setCurrentIndex(TRAIN_TAB)

    def generate_confusion_matrix(self, y_data):
        success = True
        error = ""

        message_handle = self.gui_handle.info_handle(
            "Computing confusion matrix, please wait...",
            blocking=False
        )
        QApplication.processEvents()
        try:
            confusion_matrix = self.keras_handle.confusion_matrix(
                y_data,
                self.keras_handle.predict()
            )
            self.gui_handle.training.update_confusion_matrix(confusion_matrix)
        except Exception as e:
            success = False
            error = "Failed to compute confusion matrix!\n{}".format(e)
        message_handle.close()
        message_handle.deleteLater()
        if not success:
            self.gui_handle.error_message(error)

    def load_model(self):
        title = "Load model data"
        options = QtWidgets.QFileDialog.Options()
        options |= QtWidgets.QFileDialog.DontUseNativeDialog
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, title, "", "NumPy data files (*.npy)", options=options)

        self.gui_handle.model_select.allow_update(False)

        if not filename:
            return

        d, message = self.keras_handle.load_model(filename)
        if not d["loaded"]:
            self.gui_handle.error_message(message)
            self.gui_handle.ml_state.set_model_data(None)
            return

        try:
            self.gui_handle.ml_state.set_model_data(d, source=filename)
            self.config_is_valid(show_warning=False)
            conf = self.gui_handle.get_sensor_config()
            not_found = []
            for s in d["sensor_config"].sensor:
                if s not in conf.sensor:
                    not_found.append(s)
            model_conf_dump = d["sensor_config"]._dumps()
            conf._loads(model_conf_dump)
            self.gui_handle.set_sensors(d["sensor_config"].sensor)
            self.gui_handle.feature_select.update_feature_list(d["feature_list"])
            self.gui_handle.feature_sidepanel.set_frame_settings(d["frame_settings"])
            self.gui_handle.model_select.update_layer_list(d["layer_list"])
            self.gui_handle.model_select.set_layer_shapes(d["keras_layer_info"])
            if d["y_labels"] is None:
                self.ml_state.set_training_data_status(False)
                self.ml_state.set_test_data_status(False)
            self.gui_handle.training.update_data_table(d["y_labels"], d["label_list"], loaded=True)
            self.gui_handle.model_select.dump_layers(d["layer_list"], "last_model.yaml")
        except Exception as e:
            self.gui_handle.error_message("Failed to load model data:\n{}".format(e))
            d["loaded"] = False
            self.gui_handle.ml_state.set_model_data(None)
        else:
            m = message
            if len(not_found):
                m += "\nNot all required sensors might be available!\nMissing: {}"
                m = m.format(not_found)
            self.gui_handle.info_handle(m)

    def config_is_valid(self, show_warning=True):
        model_data = self.ml_state.get_model_data()

        model_mode = None
        if model_data.get('sensor_config', None) is not None:
            config_mode = model_data["sensor_config"].mode
            if config_mode == Mode.IQ:
                model_mode = "IQ"
            elif config_mode == Mode.ENVELOPE:
                model_mode = "Envelope"
            else:
                model_mode = "Sparse"

        # Make sure the GUI has a valid sensor config
        gui_sensor_conf = self.gui_handle.get_sensor_config()
        if gui_sensor_conf is None and model_data.get('sensor_config', None) is not None:
            index = self.gui_handle.module_dd.findText(model_mode, QtCore.Qt.MatchFixedString)
            if index >= 0:
                self.gui_handle.module_dd.setCurrentIndex(index)
                self.gui_handle.update_canvas()

        if not model_data["loaded"]:
            if show_warning:
                self.gui_handle.warning_message("Model not loaded!")
            return False

        if self.gui_handle.get_gui_state("server_connected"):
            available_sensors = self.gui_handle.get_sensors()
            required_sensors = model_data["sensor_config"].sensor
            all_found = True
            for r in required_sensors:
                if r not in available_sensors:
                    all_found = False
            if not all_found:
                warning = "Sensor mismatch detected!\n"
                warning += "The model needs sensors {}!\nRun anyway?".format(required_sensors)
                if show_warning and not self.gui_handle.warning_message(warning):
                    return False
        else:
            self.gui_handle.set_sensors(model_data["sensor_config"].sensor)

        try:
            if model_mode is not None and self.gui_handle.module_dd.currentText() != model_mode:
                warning = "Service mismatch detected!\n"
                warning += "The model needs {}! Change to correct service?".format(model_mode)
                if show_warning and not self.gui_handle.warning_message(warning):
                    return False
                index = self.gui_handle.module_dd.findText(model_mode, QtCore.Qt.MatchFixedString)
                if index >= 0:
                    self.gui_handle.module_dd.setCurrentIndex(index)
                    self.gui_handle.update_canvas()
        except Exception as e:
            print(e)

        return True

    def predict(self, feature_map):
        prediction = self.keras_handle.predict(feature_map)[0]

        return prediction


class CalibrationDialog(QDialog):
    def __init__(self, calibration_data, parent):
        super().__init__(parent)

        self.setMinimumWidth(350)
        self.setModal(True)
        self.setWindowTitle("Calibration data")

        layout = QVBoxLayout()
        self.setLayout(layout)

        win = pg.GraphicsLayoutWidget()
        win.setWindowTitle("Calibration plot")
        cal_plot_image = win.addPlot(row=0, col=0)

        cal_plot = pg.ImageItem()
        cal_plot.setAutoDownsample(True)
        cal_plot_image.addItem(cal_plot)

        calibration_data -= np.nanmin(calibration_data)

        max_level = 1.2 * np.nanmax(calibration_data)

        g = 1/2.2
        calibration_data = 254/(max_level + 1.0e-9)**g * calibration_data**g

        calibration_data[calibration_data > 254] = 254

        cal_plot.updateImage(calibration_data.T, levels=(0, 256))

        lut = utils.pg_mpl_cmap("viridis")
        cal_plot.setLookupTable(lut)

        layout.addWidget(win)

        layout.addStretch(1)

        buttons_widget = QWidget(self)
        layout.addWidget(buttons_widget)
        hbox = QHBoxLayout()
        buttons_widget.setLayout(hbox)
        hbox.addStretch(1)
        cancel_btn = QPushButton("Discard")
        cancel_btn.clicked.connect(self.reject)
        hbox.addWidget(cancel_btn)
        save_btn = QPushButton("Use calibration")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self.accept)
        hbox.addWidget(save_btn)

    def get_state(self):
        return


class AugmentDataDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)

        self.setMinimumWidth(350)
        self.setModal(True)
        self.setWindowTitle("Agument data")

        layout = QVBoxLayout()
        self.setLayout(layout)

        self.offsets = []
        self.action = None

        warn = QLabel("Don't use augmentation with history dependent data!")
        description = QLabel("Select sweep offsets separated by ',' to augment data:")
        self.offsets_text = QLineEdit("-15, -10, 10, 15")
        layout.addWidget(warn)
        layout.addWidget(description)
        layout.addWidget(self.offsets_text)
        layout.addStretch(1)

        buttons_widget = QWidget(self)
        layout.addWidget(buttons_widget)
        hbox = QHBoxLayout()
        buttons_widget.setLayout(hbox)
        hbox.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.set_offsets)
        hbox.addWidget(close_btn)
        this_btn = QPushButton("This frame")
        this_btn.clicked.connect(self.set_offsets)
        hbox.addWidget(this_btn)
        all_btn = QPushButton("All frames")
        all_btn.setDefault(True)
        all_btn.clicked.connect(self.set_offsets)
        hbox.addWidget(all_btn)

    def get_state(self):
        return self.action, self.offsets

    def set_offsets(self):
        mode = self.sender().text()
        if mode == "Close":
            self.reject()
            return

        offsets = self.offsets_text.text()
        try:
            offsets = offsets.split(",")
            for idx, o in enumerate(offsets):
                self.offsets.append(int(o))
        except Exception as e:
            print("Error parsing offsets!\n", e)
            self.offsets = []
            self.reject()
            return

        if "All" in mode:
            self.action = "all"
        else:
            self.action = "current"

        self.accept()


class BatchProcessDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)

        self.setMinimumWidth(350)
        self.setModal(True)
        self.setWindowTitle("Batch processing")

        layout = QtWidgets.QGridLayout()
        self.setLayout(layout)

        self.action = {
            "process": False,
            "new_label": None,
            "processing_mode": "existing",
        }

        self.label_text = QLineEdit("")
        layout.addWidget(QLabel("Feature frame labels:"), 0, 0, 1, 2)
        layout.addWidget(self.label_text, 1, 1)

        self.radiobuttons_label = {
            "keep": QRadioButton("Keep"),
            "change": QRadioButton("Overwrite"),
        }
        for toggle in self.radiobuttons_label:
            self.radiobuttons_label[toggle].toggled.connect(self.toggle_mode)
        self.radiobuttons_label["keep"].setChecked(True)

        radio_01 = QFrame()
        radio_01.grid = QHBoxLayout()
        radio_01.grid.setContentsMargins(0, 0, 0, 0)
        radio_01.setLayout(radio_01.grid)
        radio_01.grid.addWidget(self.radiobuttons_label["keep"])
        radio_01.grid.addWidget(self.radiobuttons_label["change"])
        layout.addWidget(radio_01, 1, 0)

        layout.addWidget(QLabel(""), 2, 0)

        layout.addWidget(QLabel("Feature frame processing mode:"), 3, 0, 1, 2)
        self.radiobuttons_mode = {
            "all": QRadioButton("Redo from all sweeps"),
            "existing": QRadioButton("Change existing only"),
        }
        radio_02 = QFrame()
        radio_02.grid = QHBoxLayout()
        radio_02.grid.setContentsMargins(0, 0, 0, 0)
        radio_02.setLayout(radio_02.grid)
        radio_02.grid.addWidget(self.radiobuttons_mode["existing"])
        radio_02.grid.addWidget(self.radiobuttons_mode["all"])
        self.radiobuttons_mode["existing"].setChecked(True)
        layout.addWidget(radio_02, 4, 0, 1, 2)

        layout.addWidget(QLabel(""), 5, 0)

        buttons_widget = QWidget(self)
        layout.addWidget(buttons_widget, 6, 0, 1, 2)
        hbox = QHBoxLayout()
        buttons_widget.setLayout(hbox)
        process_btn = QPushButton("Process")
        process_btn.clicked.connect(self.set_state)
        hbox.addWidget(process_btn)
        hbox.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setDefault(True)
        cancel_btn.clicked.connect(self.set_state)
        hbox.addWidget(cancel_btn)

    def get_state(self):
        return self.action

    def toggle_mode(self):
        mode = self.sender().text()
        if "overwrite" in mode.lower():
            change = True
        else:
            change = False
        self.label_text.setEnabled(change)

    def set_state(self):
        mode = self.sender().text()
        if mode == "Process":
            self.action["process"] = True
            if self.radiobuttons_label["change"].isChecked():
                self.action["new_label"] = self.label_text.text()
            if self.radiobuttons_mode["all"].isChecked():
                self.action["processing_mode"] = "all"
            self.accept()
        else:
            self.reject()


class ModelLayerSpinBox(QFrame):
    def __init__(self, value, parent, callback=None):
        super().__init__(parent)
        self.value = value
        self.cb = callback
        width = 60
        arrow_width = 30
        height = 25

        self.grid = QtWidgets.QGridLayout(self)
        self.grid.setContentsMargins(1, 1, 1, 1)
        self.grid.setSpacing(1)
        self.grid.setAlignment(QtCore.Qt.AlignCenter)

        self.x = QPushButton("Remove")
        self.grid.addWidget(self.x, 0, 1)
        self.x.clicked.connect(partial(self._update, "x-button"))
        self.x.setFixedWidth(width)
        self.x.setFixedHeight(height)
        self.x.setStyleSheet(REMOVE_BUTTON_STYLE)

        self.up = QToolButton()
        self.up.setArrowType(QtCore.Qt.UpArrow)
        self.grid.addWidget(self.up, 0, 0)
        self.up.clicked.connect(partial(self._update, "up"))
        self.up.setFixedWidth(arrow_width)
        self.up.setFixedHeight(height)

        self.down = QToolButton()
        self.down.setArrowType(QtCore.Qt.DownArrow)
        self.grid.addWidget(self.down, 1, 0)
        self.down.clicked.connect(partial(self._update, "down"))
        self.down.setFixedWidth(arrow_width)
        self.down.setFixedHeight(height)

        self.check = QCheckBox("Active", self)
        self.check.setChecked(True)
        self.check.stateChanged.connect(partial(self._update, "is_active"))
        self.grid.addWidget(self.check, 1, 1)
        self.check.setMinimumWidth(width)
        self.check.setMaximumWidth(width)

    def _update(self, source):
        if source == "up":
            self.cb("move_layer", self.value, self.value - 1)
        elif source == "down":
            self.cb("move_layer", self.value, self.value + 1)
        elif source == "x-button":
            self.cb("remove_layer", self.value)
        elif source == "is_active":
            self.cb("is_active", self.value, self.check.isChecked())

    def update_value(self, value):
        value = max(value, 1)
        self.value = value

    def set_active(self, enabled):
        self.check.setChecked(enabled)


class SpinBoxAndSliderWidget(QFrame):
    def __init__(self, tag, callback=None):
        super().__init__()

        self.tag = tag
        self.cb = callback

        self.grid = QtWidgets.QGridLayout(self)
        self.grid.setColumnStretch(0, 7)
        self.grid.setColumnStretch(1, 3)

        label = QLabel(self)
        label.setText("Current {} position:".format(tag))
        self.grid.addWidget(label, 0, 0, 1, 1)

        self.spin_box = QSpinBox(self)
        self.spin_box.setRange(0, 100)
        self.spin_box.setSingleStep(1)
        self.spin_box.valueChanged.connect(partial(self._update, "spin_box"))
        self.spin_box.setKeyboardTracking(False)
        self.grid.addWidget(self.spin_box, 0, 1, 1, 1)

        slider_widget = QWidget()
        self.slider_range = {
            "start": QLabel("0"),
            "stop": QLabel("100"),
        }
        slider_layout = QtWidgets.QHBoxLayout(slider_widget)
        slider_layout.setContentsMargins(0, 0, 0, 0)
        slider_layout.addWidget(self.slider_range["start"])
        self.slider = QSlider(QtCore.Qt.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.sliderPressed.connect(partial(self._update, "slider"))
        self.slider.valueChanged.connect(partial(self._update, "slider"))
        slider_layout.addWidget(self.slider, 1)
        slider_layout.addWidget(self.slider_range["stop"])
        self.grid.addWidget(slider_widget, 1, 0, 1, 2)

        self.box = {
            "spin_box": self.spin_box,
            "slider": self.slider,
        }

    def _update(self, source):
        value = self.box[source].value()
        self.set_value(value)

        if self.cb is not None:
            self.cb(self.tag, value)

    def set_value(self, value):
        self.spin_box.blockSignals(True)
        self.slider.blockSignals(True)
        self.spin_box.setValue(value)
        self.slider.setValue(value)
        self.spin_box.blockSignals(False)
        self.slider.blockSignals(False)

    def set_limits(self, limits):
        for element in self.box:
            self.box[element].setRange(*limits)

        self.slider_range["start"].setText(str(limits[0]))
        self.slider_range["stop"].setText(str(limits[1]))


class Threaded_Training(QtCore.QThread):
    sig_scan = pyqtSignal(str, str, object)

    def __init__(self, training_params, parent=None):
        QtCore.QThread.__init__(self, parent)

        self.parent = parent
        self.training_params = training_params
        self.model = training_params["model"]
        self.epochs = training_params["epochs"]

        self.finished.connect(self.stop_thread)

        self.stop_now = False

    def stop_thread(self):
        self.stop_now = True
        self.skip = True
        self.quit()

    def run(self):
        self.training_params["plot_cb"] = self.update_plots
        self.training_params["stop_cb"] = self.stop_training
        self.training_params["threaded"] = True
        self.parent.is_training(True)

        try:
            training_model, session, graph = self.model.train(self.training_params)
            self.emit("training_done", "", [training_model, session, graph])
        except Exception as e:
            msg = "Failed to train model!\n{}".format(self.format_error(e))
            self.emit("training_error", msg)
        self.parent.is_training(False)

    def receive(self, message_type, message, data=None):
        if message_type == "stop":
            self.stop_now = True
        else:
            print("Scan thread received unknown signal: {}".format(message_type))

    def emit(self, message_type, message, data=None):
        self.sig_scan.emit(message_type, message, data)

    def update_plots(self, data):
        self.sig_scan.emit("update_plots", "", data)

    def format_error(self, e):
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        err = "{}\n{}\n{}\n{}".format(exc_type, fname, exc_tb.tb_lineno, e)
        return err

    def stop_training(self):
        return self.stop_now


class Threaded_BatchProcess(QtCore.QThread):
    sig_scan = pyqtSignal(str, str, object)

    def __init__(self, processing_params, gui_handle, parent=None):
        QtCore.QThread.__init__(self, parent)

        self.parent = parent
        self.processing_params = processing_params
        self.feature_process = None
        self.skipped_files = []
        self.gui_handle = gui_handle
        self.finished.connect(self.stop_thread)
        self.skip = False
        self.stop = False
        self.total_progress = 0
        self.progress_steps = 0

    def stop_thread(self):
        self.emit("batch_process_stopped", "" , "")
        self.emit("skipped_files", "", self.skipped_files)
        self.quit()

    def run(self):
        nr_files = len(self.processing_params["file_list"])
        self.progress_steps = 100 / nr_files
        first = True
        for i, filename in enumerate(self.processing_params["file_list"]):
            self.skip = False
            self.total_progress = i / nr_files * 100
            self.update_progress()
            if self.stop:
                break
            try:
                data = np.load(filename, allow_pickle=True)
            except Exception:
                traceback.print_exc()
                self.skipped_files.append((filename, "Failed to load"))
                continue

            try:
                sweep_data = recording.unpack(data.item()["sweep_data"])
                fdata = data.item()["frame_data"]
                sensor_config = data.item()["sensor_config"]
                conf = configs.load(sensor_config)
                data_len = len(sweep_data.data.data)
            except Exception:
                traceback.print_exc()
                self.skipped_files.append((filename, "Failed to load"))
                continue

            if first:
                first = False
                self.emit("update_sensor_config", "", conf)

            module_info = MODULE_KEY_TO_MODULE_INFO_MAP[sweep_data.module_key]
            index = self.gui_handle.module_dd.findText(
                module_info.label,
                QtCore.Qt.MatchFixedString
            )

            if self.gui_handle.module_dd.currentIndex() == 0:
                self.emit("set_module", "", index)
            elif index != self.gui_handle.module_dd.currentIndex():
                self.skipped_files.append((filename, "Module mismatch"))
                continue

            if self.processing_params["new_label"] is None:
                try:
                    label = fdata["ml_frame_data"]["current_frame"]["label"]
                except Exception:
                    self.skipped_files.append((filename, "No label"))
                    continue
            else:
                label = self.processing_params["new_label"]
            self.emit("set_label", "", label)

            # Keep backwards compatibility
            if "iq_data" in fdata:
                fdata["sweep_data"] = fdata.pop("iq_data")

            updated_data = {
                "sweep_buffer": data_len,
                "replay_buffered": True,
                "sensors": conf.sensor,
                "sweep_data": sweep_data,
                "ml_data": fdata,
            }

            info_txt = "Found data with {} sweeps and {} feature frames.".format(
                data_len,
                len(fdata["ml_frame_data"]["frame_list"]),
            )
            _, file = os.path.split(filename)
            self.emit("update_file_info", "", [file, info_txt])

            if self.processing_params["processing_mode"] == "existing":
                res = self.change_existing_only(fdata, sweep_data, conf)
                if res != "success":
                    self.skipped_files.append((filename, "Processing {}".format(res)))
                    continue
                else:
                    updated_data["ml_data"] = fdata
                    self.emit("update_data", "", updated_data)
            else:
                self.emit("update_data", "", updated_data)
                try:
                    self.emit("start_scan", "", "")
                    time.sleep(0.5)
                    while self.gui_handle.buttons["stop"].isEnabled() and not self.skip:
                        self.update_progress(self.gui_handle.num_recv_frames / data_len * 100)
                        QApplication.processEvents()
                except Exception:
                    traceback.print_exc()
                    self.skipped_files.append((filename, "Processing failed"))
                    continue

                if self.skip or self.stop:
                    self.skipped_files.append((filename, "Processing skipped"))
                    continue

            try:
                if not self.skip and not self.stop:
                    f = filename[:-3] + "_batch_processed.npy"
                    self.emit("save_data", "", f)
            except Exception:
                traceback.print_exc()
                self.skipped_files.append((filename, "Failed to save"))
                continue

        self.stop_thread()

    def change_existing_only(self, fdata, sweep_data, conf):
        updated_feature_list = self.gui_handle.feature_select.get_feature_list()
        updated_frame_settings = self.gui_handle.feature_sidepanel.get_frame_settings()
        fdata["ml_frame_data"]["feature_list"] = updated_feature_list
        fdata["ml_frame_data"]["frame_info"]["frame_pad"] = updated_frame_settings["frame_pad"]
        fdata["ml_frame_data"]["frame_info"]["frame_size"] = updated_frame_settings["frame_size"]
        fdata["sensor_config"] = conf
        if self.feature_process is None:
            self.feature_process = feature_proc.FeatureProcessing(fdata["sensor_config"])
            self.feature_process.set_feature_list(updated_feature_list)
            self.feature_process.set_frame_settings(updated_frame_settings)
        frame_list = fdata["ml_frame_data"]["frame_list"]

        nr_frames = len(frame_list)
        try:
            for nr, frame in enumerate(frame_list):
                self.update_progress(file_progress=(nr / nr_frames * 100))
                if self.processing_params["new_label"] is not None:
                    label = self.processing_params["new_label"]
                else:
                    label = frame["label"]
                frame_start = frame["frame_marker"]
                fdata = self.feature_process.feature_extraction_window(
                    fdata,
                    sweep_data,
                    frame_start,
                    label
                )
                # Replace old feature frame with updated frame
                f_modified = fdata["ml_frame_data"]["current_frame"]
                for key in f_modified:
                    frame[key] = f_modified[key]

                if self.skip:
                    return "skipped"
        except Exception:
            traceback.print_exc()
            return "failed"
        return "success"

    def receive(self, message_type, message, data=None):
        if message_type in ["stop", "skip_file"]:
            if message_type == "stop":
                self.stop = True
                self.skip = True
            else:
                self.skip = True

            if self.processing_params["processing_mode"] == "all":
                self.emit("stop_scan", "", "")

            if message_type == "stop":
                self.stop_thread()
        else:
            print("Batch process thread received unknown signal: {}".format(message_type))

    def emit(self, message_type, message, data=None):
        self.sig_scan.emit(message_type, message, data)

    def update_progress(self, file_progress=0):
        total = self.total_progress + self.progress_steps * file_progress / 100
        self.sig_scan.emit("update_progress", "", [file_progress, total])

    def stop_processing(self):
        return self.stop


class ProgressBar(QDialog):
    def __init__(self, thread_send):
        super().__init__()

        self.setMinimumWidth(500)
        self.setModal(True)
        self.setWindowTitle("Batch processing progress")

        self.thread_send = thread_send

        self.grid = QtWidgets.QGridLayout(self)
        self.grid.setContentsMargins(1, 1, 1, 1)
        self.grid.setSpacing(1)

        self.total_progress = QProgressBar(self)
        self.file_progress = QProgressBar(self)

        self.btn_skip_file = QPushButton('Skip file', self)
        self.btn_skip_file.clicked.connect(self.skip_file)

        self.btn_cancel = QPushButton('Cancel', self)
        self.btn_cancel.clicked.connect(self.cancel)

        self.file_name = QLabel("")
        self.file_props = QLabel("")

        self.grid.addWidget(self.file_name, 0, 0, 1, 6)
        self.grid.addWidget(QLabel(""), 1, 0)
        self.grid.addWidget(self.file_props, 2, 0, 1, 6)
        self.grid.addWidget(QLabel(""), 3, 0)
        self.grid.addWidget(QLabel("Total:"), 4, 0)
        self.grid.addWidget(self.total_progress, 4, 1, 1, 6)
        self.grid.addWidget(QLabel(""), 5, 0)
        self.grid.addWidget(QLabel("Current:"), 6, 0)
        self.grid.addWidget(self.file_progress, 6, 1, 1, 6)
        self.grid.addWidget(QLabel(""), 7, 0)
        self.grid.addWidget(self.btn_skip_file, 8, 0)
        self.grid.addWidget(self.btn_cancel, 8, 6)

        self.grid.setRowStretch(1, 2)

    def skip_file(self):
        self.thread_send("skip_file", "", "")

    def cancel(self):
        self.thread_send("stop", "", "")
        try:
            self.reject()
        except Exception:
            # Might be closed already
            pass

    def update_progress(self, progress):
        self.file_progress.setValue(progress[0])
        self.total_progress.setValue(progress[1])

    def update_file_info(self, info):
        self.file_name.setText("File: " + info[0])
        self.file_props.setText(info[1])
