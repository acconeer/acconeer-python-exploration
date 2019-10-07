import datetime
import numpy as np
import sys
import os
import colorsys
import pyqtgraph as pg
from functools import partial

from PyQt5 import QtCore, QtWidgets
from PyQt5.QtWidgets import (QComboBox, QApplication, QWidget, QLabel, QLineEdit,
                             QCheckBox, QFrame, QPushButton, QRadioButton,
                             QSpinBox, QSlider, QTableWidget, QTableWidgetItem
                             )
from PyQt5.QtGui import QColor, QBrush
from PyQt5.QtCore import pyqtSignal

import keras_processing as kp
import feature_processing as feature_proc
import feature_definitions as feature_def
from helper import SensorSelection, QHLine, QVLine, Count, GUI_Styles, ErrorFormater
from acconeer_utils import example_utils


class FeatureSelectFrame(QFrame):
    def __init__(self, parent, gui_handle=None):
        super().__init__()
        self.styles = GUI_Styles()
        self.nr_col = 13
        self.row_idx = Count(2)
        self.gui_handle = gui_handle
        self.has_valid_config = False
        self.feature_testing = False

        self.limits = {
            "start": 0,
            "end": np.inf,
            "sensors": [1, 2, 3, 4],
            "data_type": "envelope",
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
        self.feature_frame_scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.feature_frame_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.feature_frame_scroll.setMinimumWidth(1000)
        self.feature_frame_scroll.setMinimumHeight(350)

        self.feature_frame = QFrame(self.feature_frame_scroll)
        self.feature_frame_scroll.setWidget(self.feature_frame)

        self.main.addWidget(self.feature_frame_scroll)
        self._layout = QtWidgets.QGridLayout(self.feature_frame)
        self._layout.setContentsMargins(10, 5, 10, 5)
        self._layout.setSpacing(10)
        self.feature_frame.setLayout(self._layout)

        self.enabled_features = []
        self.features = feature_def.get_features()

        self.enabled_count = Count()
        self.create_grid()
        self.parse_features()
        self.create_feature_plot()

        self.drop_down.setCurrentIndex(1)

    def create_grid(self):
        self._layout.addWidget(QLabel("Feature"), 0, 0)
        self._layout.addWidget(QLabel("Parameters"), 0, 2, 1, 9)
        self._layout.addWidget(QLabel("Sensors"), 0, 10)
        self._layout.addWidget(QHLine(), 1, 0, 1, self.nr_col)
        self.name_vline = QVLine()
        self.params_vline = QVLine()
        self.sensor_vline = QVLine()
        self.error_text = QLabel("")
        self.error_text.setStyleSheet("QLabel {color: red}")

        self.buttons = {
            "start": QPushButton("Test extraction", self),
            "stop": QPushButton("Stop", self),
            "replay_buffered": QPushButton("Replay buffered", self),
        }

        for b in self.buttons:
            button = self.buttons[b]
            button.clicked.connect(partial(self.gui_handle.buttons[b].click))
            button.setEnabled(False)

    def update_grid(self):
        try:
            self._layout.removeWidget(self.name_vline)
            self._layout.removeWidget(self.params_vline)
            self._layout.removeWidget(self.sensor_vline)
            self._layout.removeWidget(self.drop_down)
            self._layout.removeWidget(self.error_text)
            for b in self.buttons:
                self._layout.removeWidget(self.button[b])
        except Exception:
            pass

        self._layout.addWidget(self.name_vline, 0, 1, self.row_idx.val + 1, 1)
        self._layout.addWidget(self.params_vline, 0, 9, self.row_idx.val + 1, 1)
        self._layout.addWidget(self.sensor_vline, 0, 11, self.row_idx.val + 1, 1)
        self._layout.addWidget(self.drop_down, self.row_idx.pre_incr(), 0, 1, 4)
        self._layout.addWidget(self.buttons["start"], self.row_idx.val, 4)
        self._layout.addWidget(self.buttons["stop"], self.row_idx.val, 5)
        self._layout.addWidget(self.buttons["replay_buffered"], self.row_idx.val, 6)
        self._layout.addWidget(self.error_text, self.row_idx.val, 7, 1, self.nr_col - 7)

        self.drop_down.setCurrentIndex(0)

        self._layout.setRowStretch(self.row_idx.val + 2, 1)

        self.update_feature_plot()

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

        self.drop_down = QComboBox(self)
        self.drop_down.setStyleSheet("background-color: white")
        self.drop_down.addItem("Add feature")
        for key in self.feature_list:
            self.drop_down.addItem(self.feature_list[key]["name"])

        self.drop_down.currentIndexChanged.connect(self.add_features_details)
        self._layout.addWidget(self.drop_down, 2, 0, 1, 6)

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

        self._layout.removeWidget(self.drop_down)

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
        row = self.row_idx.val

        other_items = []
        other_items.append(QLabel(name))
        self._layout.addWidget(other_items[0], row, self.num)
        c = example_utils.color_cycler(self.enabled_count.pre_incr())
        other_items[0].setStyleSheet("background-color: {}".format(c))

        options = {}
        for (text, value, limits, data_type) in opts:
            labels[text] = QLabel(text)
            textboxes[text] = QLineEdit(str(value))
            textboxes[text].setStyleSheet("background-color: white")
            textboxes[text].editingFinished.connect(
                partial(self.update_feature_params, limits, data_type, value)
                )
            options[text] = textboxes[text]
            self._layout.addWidget(labels[text], row, self.increment())
            self._layout.addWidget(textboxes[text], row, self.increment())

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

        self._layout.addWidget(sensors, row, 10)

        c_button = QPushButton("remove", self)
        c_button.setStyleSheet(self.styles.get_button_style())
        c_button.clicked.connect(self.remove_feature)

        self._layout.addWidget(c_button, row, 12)

        self.num = -1
        row = self.row_idx.pre_incr()

        out_data = {}
        other_items.append(QLabel("Output [{}D]".format(model)))
        self._layout.addWidget(other_items[1], row, self.increment())
        for o in output:
            out_data[o] = QCheckBox(output[o], self)
            out_data[o].stateChanged.connect(self.update_feature_plot)
            self._layout.addWidget(out_data[o], row, self.increment())
            if self.num == 3:
                out_data[o].setChecked(True)
            if len(output) == 1:
                out_data[o].setVisible(False)

        other_items.append(QHLine())

        self._layout.addWidget(other_items[2], self.row_idx.pre_incr(), 0, 1, self.nr_col)

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
            "sensor_data_type": sensor_data_type
        }

        self.enabled_features.append(feature_params)

        self.update_grid()

    def remove_feature(self, clear_all=False):
        if not clear_all:
            button = self.sender()
            button_idx = self._layout.indexOf(button)
            pos = self._layout.getItemPosition(button_idx)
            list_pos = [int((pos[0] - 2) / 3)]
        else:
            list_pos = list(range(len(self.enabled_features)))

        pop_list = []
        for lpos in list_pos:
            for idx, feature in enumerate(self.enabled_features):

                if idx < lpos:
                    continue

                widgets = []
                widgets.append(feature["sensors"])
                widgets.append(feature["c_button"])

                for i in feature["other_items"]:
                    widgets.append(i)

                for key in feature["textboxes"]:
                    widgets.append(feature["textboxes"][key])
                    widgets.append(feature["labels"][key])

                for key in feature["output"]:
                    widgets.append(feature["output"][key])

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
            self.row_idx.decr(val=4)
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
            entry["cb"] = feat["cb"]
            entry["sensors"] = feat["sensors"].get_sensors()

            for s in entry["sensors"]:
                if s not in list_of_sensors:
                    list_of_sensors.insert(s - 1, s)

            entry["options"] = {}
            if feat["options"] is not None:
                for opt in feat["options"]:
                    opt_cb = feat["options"][opt]
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

    def update_feature_list(self, saved_feature_list):
        # check if feature list is valid
        for feat in saved_feature_list:
            feature = {}
            feature["key"] = feat["key"]
            feature["name"] = feat["name"]
            feature["class"] = feat["cb"]
            feature["sensors"] = feat["sensors"]

        self.remove_feature(clear_all=True)

        error_message = "Feature Classes not found:<br>"
        all_found = True
        for feature in saved_feature_list:
            try:
                feature_key = feature["key"]
                self.add_features_details(None, key=feature_key)
            except Exception:
                error_message += ("Feature Name: {}<br>".format(feature["name"]))
                all_found = False
            else:
                if feature_key in self.feature_list:
                    e_feat = self.enabled_features[-1]
                    e_feat["sensors"].set_sensors(feature["sensors"])

                    if feature["options"] is not None:
                        for opt in feature["options"]:
                            opt_textbox = e_feat["options"][opt]
                            opt_textbox.setText(str(feature["options"][opt]))

                    if feature["output"] is not None:
                        for out in feature["output"]:
                            out_checkbox = e_feat["output"][out]
                            out_checkbox.setChecked(feature["output"][out])

        if not all_found:
            try:
                self.gui_handle.error_message(error_message)
            except Exception:
                print(error_message)

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
        if sensor_config is None:
            sensor_config = self.gui_handle.save_gui_settings_to_sensor_config()

        self.get_feature_list()
        feat_start = self.limits["start"]
        feat_end = self.limits["end"]
        feat_sensors = self.limits["sensors"]
        feature_data_types = self.limits["sensor_data_types"]
        model_dimensions = self.limits["model_dimensions"]
        error_message = None

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
        except Exception:
            if error_handle is None:
                return self.error_text.setText("No service selected!")
            else:
                error_message("Sensor_config has wrong format!")
                return False

        config_is_valid["start"][1] = config_start
        if feat_start >= config_start and feat_start < config_end:
            config_is_valid["start"][2] = True

        config_is_valid["end"][1] = config_end
        if feat_end <= config_end:
            config_is_valid["end"][2] = True

        config_is_valid["sensors"][1] = config_sensors
        config_is_valid["sensors"][2] = True

        if len(feat_sensors) > len(config_sensors):
            for sensor in feat_sensors:
                if sensor not in config_sensors:
                    config_is_valid["sensors"][2] = False
                    break

        is_valid = True
        for k in config_is_valid:
            if not config_is_valid[k][2]:
                if error_message is None:
                    error_message = "Configuration missmatch detected:<br>"
                error_message += "Settings for {}:<br> Features: {}<br>Sensor: {}<br>".format(
                    k,
                    config_is_valid[k][0],
                    config_is_valid[k][1],
                    )
                is_valid = False

        if len(model_dimensions) > 1:
            is_valid = False
            err = "Features with different model dimensions detected:<br>"
            if error_message is None:
                error_message = err
            else:
                error_message += err
            error_message += "{}<br>".format(model_dimensions)

        data_types_valid = True
        if "sparse" in feature_data_types and "sparse" not in config_data_type:
            data_types_valid = False
        if "iq" in feature_data_types and "iq" not in config_data_type:
            data_types_valid = False
        if "iq" in feature_data_types and "sparse" in feature_data_types:
            data_types_valid = False

        if not data_types_valid:
            is_valid = False
            err = "Inconsistent sensor data types detected:<br>"
            if error_message is None:
                error_message = err
            else:
                error_message += err
            error_message += "Features: "
            for d in feature_data_types:
                error_message += "{} ".format(d)
            error_message += "<br>Sensor: {}<br>".format(config_data_type)

        if not is_valid:
            self.buttons["start"].setEnabled(False)
            self.buttons["replay_buffered"].setEnabled(False)
            self.has_valid_config = False
            if error_handle is None:
                self.error_text.setText(error_message)
            else:
                error_handle(error_message)
            return False
        else:
            self.has_valid_config = True
            if self.gui_handle.get_gui_state("server_connected"):
                self.buttons["start"].setEnabled(True)
                if self.gui_handle.data is not None:
                    self.buttons["replay_buffered"].setEnabled(True)
            self.error_text.setText("")
            return True

    def is_config_valid(self):
        return self.has_valid_config

    def clearLayout(self):
        while self._layout.count():
            child = self._layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def create_feature_plot(self):
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

        lut = example_utils.pg_mpl_cmap("viridis")
        self.feat_plot.setLookupTable(lut)

        self.feature_areas = []
        self.main.addWidget(win)

    def update_feature_params(self, limits, data_type, default):
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
                    rect.setPen(example_utils.pg_pen_cycler(feature["count"]))
                    rect.setBrush(example_utils.pg_brush_cycler(feature["count"]))
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

    def plot_feature(self,  data):
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

        return

    def get_frame_size(self):
        if hasattr(self.gui_handle, "feature_sidepanel"):
            frame_size = self.gui_handle.feature_sidepanel.get_frame_settings()["frame_size"]
        else:
            frame_size = 30

        return frame_size


class FeatureExtractFrame(QFrame):
    def __init__(self, parent, gui_handle=None):
        super().__init__()

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

        self.textboxes["label"].setStyleSheet("background-color: lightcoral")
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
    def __init__(self, parent, gui_handle):
        super().__init__()

        self.gui_handle = gui_handle
        self.grid = QtWidgets.QGridLayout(self)
        self.grid.setContentsMargins(9, 0, 9, 9)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)

        self.format_error = ErrorFormater()

        self.frame_settings = {}

        self.labels = {
            "frame_time": QLabel("Frame time [s]"),
            "sweep_rate": QLabel("Sweep rate [Hz]"),
            "frame_size": QLabel("Sweeps per frame"),
            "auto_thrshld_offset": QLabel("Thrshld/Offset:"),
            "dead_time": QLabel("Dead time:"),
            "save_load": QLabel("Save/load feature settings:"),
            "frame_settings": QLabel("Frame settings:"),
            "collection_mode": QLabel("Feature collection mode:"),
            "empty_1": QLabel(""),
            "empty_2": QLabel(""),
            "empty_3": QLabel(""),
        }
        self.textboxes = {
            "frame_time": QLineEdit(str(1)),
            "sweep_rate": QLineEdit(str(30)),
            "frame_size": QLineEdit(str(30)),
            "auto_threshold": QLineEdit("1.5"),
            "dead_time": QLineEdit("10"),
            "auto_offset": QLineEdit("5"),
        }

        self.h_lines = {
            "h_line_1": QHLine(),
            "h_line_2": QHLine(),
            "h_line_3": QHLine(),
        }

        self.buttons = {
            "load_settings": QPushButton("Load settings", self),
            "save_settings": QPushButton("Save settings", self),
            "load_session": QPushButton("Load session", self),
            "save_session": QPushButton("Save session", self),
            "trigger": QPushButton("&Trigger", self),
        }

        self.buttons["load_settings"].clicked.connect(self.load_data)
        self.buttons["load_session"].clicked.connect(self.load_data)
        self.buttons["save_settings"].clicked.connect(self.save_data)
        self.buttons["save_session"].clicked.connect(self.save_data)
        self.buttons["trigger"].clicked.connect(
            lambda: self.gui_handle.sig_scan.emit(
                "update_feature_extraction",
                "triggered",
                True
                )
            )

        self.checkboxes = {
            "rolling": QCheckBox("Rolling frame", self),
        }
        self.checkboxes["rolling"].clicked.connect(
            lambda: self.gui_handle.sig_scan.emit(
                "update_feature_extraction",
                "rolling",
                self.checkboxes["rolling"].isChecked()
                )
            )

        self.radiobuttons = {
            "auto": QRadioButton("auto"),
            "single": QRadioButton("single"),
            "continuous": QRadioButton("cont."),
        }

        self.radiobuttons["auto"].setChecked(True)
        self.radio_frame = QFrame()
        self.radio_frame.grid = QtWidgets.QGridLayout(self.radio_frame)
        self.radio_frame.grid.setContentsMargins(0, 0, 0, 0)
        self.radio_frame.grid.addWidget(self.labels["collection_mode"], 0, 0, 1, 3)
        self.radio_frame.grid.addWidget(self.h_lines["h_line_2"], 1, 0, 1, 3)
        self.radio_frame.grid.addWidget(self.radiobuttons["auto"], 2, 0)
        self.radio_frame.grid.addWidget(self.radiobuttons["single"], 2, 1)
        self.radio_frame.grid.addWidget(self.radiobuttons["continuous"], 2, 2)
        self.radio_frame.grid.addWidget(self.checkboxes["rolling"], 3, 0, 1, 2)
        self.radio_frame.grid.addWidget(self.buttons["trigger"], 4, 0, 1, 3)
        self.radio_frame.grid.addWidget(self.labels["auto_thrshld_offset"], 5, 0)
        self.radio_frame.grid.addWidget(self.textboxes["auto_threshold"], 5, 1)
        self.radio_frame.grid.addWidget(self.textboxes["auto_offset"], 5, 2)
        self.radio_frame.grid.addWidget(self.labels["dead_time"], 6, 0)
        self.radio_frame.grid.addWidget(self.textboxes["dead_time"], 6, 1, 1, 2)

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
        self.frame_settings_storage()

        for key in self.textboxes:
            if key in ["auto_threshold", "dead_time", "auto_offset"]:
                continue
            self.textboxes[key].editingFinished.connect(partial(self.calc_values, key, False))
            self.textboxes[key].textChanged.connect(partial(self.calc_values, key, True))

        self.num = 0
        self.grid.addWidget(self.labels["frame_settings"], self.increment(), 0, 1, 2)
        self.grid.addWidget(self.h_lines["h_line_1"], self.increment(), 0, 1, 2)
        self.grid.addWidget(self.labels["frame_time"], self.increment(), 0)
        self.grid.addWidget(self.textboxes["frame_time"], self.num, 1)
        self.grid.addWidget(self.labels["sweep_rate"], self.increment(), 0)
        self.grid.addWidget(self.textboxes["sweep_rate"], self.num, 1)
        self.grid.addWidget(self.labels["frame_size"], self.increment(), 0)
        self.grid.addWidget(self.textboxes["frame_size"], self.num, 1)
        self.grid.addWidget(self.labels["empty_1"], self.increment(), 0, 1, 2)
        self.grid.addWidget(self.radio_frame, self.increment(), 0, 1, 2)
        self.grid.addWidget(self.labels["empty_2"], self.increment(), 0, 1, 2)
        self.grid.addWidget(self.labels["save_load"], self.increment(), 0, 1, 2)
        self.grid.addWidget(self.h_lines["h_line_3"], self.increment(), 0, 1, 2)
        self.grid.addWidget(self.buttons["load_settings"], self.increment(), 0)
        self.grid.addWidget(self.buttons["save_settings"], self.num, 1)
        self.grid.addWidget(self.buttons["load_session"], self.increment(), 0)
        self.grid.addWidget(self.buttons["save_session"], self.num, 1)

        self.textboxes["frame_size"].setEnabled(False)

        self.grid.setRowStretch(self.increment(), 1)

        self.modes = {
            "feature_select": [
                self.labels["empty_1"],
                self.h_lines["h_line_2"],
                self.labels["collection_mode"],
                self.radio_frame,
                ],
            "feature_extract": [
                self.labels["frame_time"],
                self.labels["sweep_rate"],
                self.textboxes["frame_time"],
                self.textboxes["sweep_rate"],
                ],
            "feature_inspect": [
                self.labels["frame_time"],
                self.labels["sweep_rate"],
                self.textboxes["frame_time"],
                self.textboxes["sweep_rate"],
                self.labels["empty_1"],
                self.h_lines["h_line_2"],
                self.labels["collection_mode"],
                self.radio_frame,
                ],
            "eval": [
                self.labels["empty_1"],
                self.labels["empty_2"],
                self.labels["frame_settings"],
                self.labels["save_load"],
                self.labels["frame_time"],
                self.labels["sweep_rate"],
                self.labels["frame_size"],
                self.h_lines["h_line_1"],
                self.h_lines["h_line_3"],
                self.textboxes["frame_time"],
                self.textboxes["sweep_rate"],
                self.textboxes["frame_size"],
                self.buttons["load_session"],
                self.buttons["save_session"],
                self.buttons["load_settings"],
                self.buttons["save_settings"],
                ],
            "train": [],
        }

    def frame_settings_storage(self, senders=None):
        if senders is None:
            senders = [
                "frame_label",
                "frame_size",
                "sweep_rate",
                "collection_mode",
                "auto_threshold",
                "auto_offset",
                "dead_time",
                "rolling",
                "sweep_rate",
            ]
        elif not isinstance(senders, list):
            senders = [senders]

        for sender in senders:
            try:
                if sender == "frame_label":
                    self.frame_settings[sender] = self.gui_handle.feature_extract.get_label()
                elif sender in ["frame_size", "sweep_rate", "dead_time", "auto_offset"]:
                    self.frame_settings[sender] = int(self.textboxes[sender].text())
                elif sender in ["frame_time", "auto_threshold"]:
                    self.frame_settings[sender] = float(self.textboxes[sender].text())
                elif sender == "rolling":
                    self.frame_settings[sender] = self.checkboxes[sender].isChecked()
            except Exception as e:
                print("Wrong settings for {}:\n{}".format(sender, e))

            if sender == "collection_mode":
                self.frame_settings["collection_mode"] = self.radio_toggles()

        sig = None
        if self.gui_handle.get_gui_state("scan_is_running"):
            sig = self.gui_handle.sig_scan

            # Only allow hot updating frame size when feature select preview
            if self.gui_handle.get_gui_state("ml_tab") == "feature_select":
                sender = "frame_size"
                senders = [sender]

            if len(senders) > 1:
                sig.emit("update_feature_extraction", None, self.frame_settings)
            else:
                sig.emit("update_feature_extraction", sender, self.frame_settings[senders[0]])

    def get_frame_settings(self):
        self.frame_settings_storage()
        return self.frame_settings

    def set_frame_settings(self, frame_settings):
        try:
            self.gui_handle.feature_extract.set_label(frame_settings["frame_label"])
            self.textboxes["frame_time"].setText(str(frame_settings["frame_time"]))
            self.textboxes["sweep_rate"].setText(str(frame_settings["sweep_rate"]))
            self.textboxes["dead_time"].setText(str(frame_settings["dead_time"]))
            self.textboxes["auto_threshold"].setText(str(frame_settings["auto_threshold"]))
            self.textboxes["auto_offset"].setText(str(frame_settings["auto_offset"]))
            self.radiobuttons[frame_settings["collection_mode"]].setChecked()
            self.checkboxes["rolling"].setChecked(frame_settings["rolling"])
        except Exception:
            pass

        self.frame_settings_storage()

    def calc_values(self, key, edditing):
        try:
            frame_time = float(self.textboxes["frame_time"].text())
            sweep_rate = int(self.textboxes["sweep_rate"].text())
        except Exception:
            if not edditing:
                print("{} is not a valid input for {}!".format(self.textboxes[key].text(), key))
                if key == "frame_time":
                    self.textboxes["frame_time"].setText("1")
                if key == "sweep_rate":
                    self.textboxes["sweep_rate"].setText(
                        self.gui_handle.textboxes["sweep_rate"].text()
                        )
                return
            else:
                return

        if not edditing:
            if frame_time == 0:
                self.textboxes["frame_time"].setText("1")
                frame_time = 1

        if key == "sweep_rate":
            self.gui_handle.textboxes["sweep_rate"].setText(self.textboxes["sweep_rate"].text())

        sweeps = int(sweep_rate * frame_time)

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

        if self.radiobuttons["auto"].isChecked():
            self.labels["auto_thrshld_offset"].show()
            self.textboxes["auto_threshold"].show()
            self.labels["dead_time"].show()
            self.textboxes["dead_time"].show()
            self.textboxes["auto_offset"].show()
        if self.radiobuttons["continuous"].isChecked():
            self.checkboxes["rolling"].show()
        if self.radiobuttons["single"].isChecked():
            self.buttons["trigger"].show()

        for m in self.radiobuttons:
            if self.radiobuttons[m].isChecked():
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

        options = QtWidgets.QFileDialog.Options()
        options |= QtWidgets.QFileDialog.DontUseNativeDialog
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, title, "", "NumPy data files (*.npy)", options=options)

        if filename:
            try:
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
        else:
            try:
                sweep_data = data.item()["sweep_data"]
                frame_data = data.item()["frame_data"]
                feature_list = data.item()["feature_list"]
                self.gui_handle.feature_select.update_feature_list(feature_list)
                try:
                    self.gui_handle.feature_extract.set_label(
                        frame_data["ml_frame_data"]["current_frame"]["label"]
                        )
                except Exception as e:
                    error_text = self.format_error.error_to_text(e)
                    print("No label stored ({})".format(error_text))

                module_label = sweep_data[0]["service_type"]
                data_len = len(sweep_data)
                conf = sweep_data[0]["sensor_config"]
                index = self.gui_handle.module_dd.findText(
                    module_label,
                    QtCore.Qt.MatchFixedString
                    )
                if index >= 0:
                    self.gui_handle.module_dd.setCurrentIndex(index)
                    self.gui_handle.update_canvas()
                self.gui_handle.load_gui_settings_from_sensor_config(conf)
                self.gui_handle.textboxes["sweep_buffer"].setText(str(data_len))
                self.gui_handle.buttons["replay_buffered"].setEnabled(True)
                self.gui_handle.set_sensors(conf.sensor)
                self.gui_handle.data = sweep_data
                self.gui_handle.ml_data = frame_data
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

            try:
                frame_settings = data.item()["frame_settings"]
                self.gui_handle.feature_sidepanel.set_frame_settings(frame_settings)
            except Exception as e:
                error_text = self.format_error.error_to_text(e)
                error_handle("Failed to load frame settings:<br> {}".format(error_text))

    def save_data(self):
        feature_list = self.gui_handle.feature_select.get_feature_list()
        action = self.sender().text()

        title = "Save feature settings"
        fname = 'ml_feature_settings_{date:%Y_%m_%d_%H%M}'.format(date=datetime.datetime.now())
        if "session" in action:
            title = "Save session data"
            fname = 'ml_session_data_{date:%Y_%m_%d_%H%M}'.format(date=datetime.datetime.now())

        options = QtWidgets.QFileDialog.Options()
        options |= QtWidgets.QFileDialog.DontUseNativeDialog
        file_types = "NumPy data files (*.npy)"

        filename, info = QtWidgets.QFileDialog.getSaveFileName(
            self, title, fname, file_types, options=options)

        if not filename:
            return

        data = {
                "feature_list": feature_list,
            }
        if "session" in action:
            title = "Save session data"
            data = {
                "feature_list": self.gui_handle.ml_data["ml_frame_data"]["feature_list"],
                "sweep_data": self.gui_handle.data,
                "frame_data": self.gui_handle.ml_data,
                "frame_settings": self.gui_handle.feature_sidepanel.get_frame_settings()
                }

        try:
            np.save(filename, data, allow_pickle=True)
        except Exception as e:
            self.gui_handle.error_message("Failed to save settings:\n {}".format(e))
            return


class FeatureInspectFrame(QFrame):
    def __init__(self, parent, gui_handle=None):
        super().__init__()

        self.current_sweep = 0
        self.current_frame_nr = -1
        self.current_frame_data = None
        self.nr_col = 2

        self.feature_process = None
        self.gui_handle = gui_handle
        self.grid = QtWidgets.QGridLayout(self)
        self.grid.setContentsMargins(9, 0, 9, 9)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)

        self.graph = LabelingGraph(self)

        self.labels = {
            "update": QLabel("Update frame data: "),
            "current_frame": QLabel("Frame: NA"),
            "current_sweep": QLabel("Sweep: NA"),
            "adv_sweeps": QLabel("Advance sweeps: "),
            "adv_frame": QLabel("Advance frame: "),
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
        }

        for i in self.buttons:
            if "update" in i:
                self.buttons[i].clicked.connect(self.update_frame_data)

        self.update_box = QFrame()
        self.update_box.grid = QtWidgets.QGridLayout(self.update_box)
        self.update_box.grid.addWidget(self.labels["label"], 0, 0, 1, 2)
        self.update_box.grid.addWidget(self.textboxes["label"], 1, 0, 1, 2)
        self.update_box.grid.addWidget(self.labels["current_frame"], 2, 0)
        self.update_box.grid.addWidget(self.labels["current_sweep"], 2, 1)
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
        f_current = fdata["ml_frame_data"]["current_frame"]
        f_info = fdata["ml_frame_data"]["frame_info"]

        frame_nr = self.current_frame_nr
        if action == "frames":
            frame_nr = max(0, number - 1)
        total_frames = len(f_histdata) - 1
        frame_nr = int(min(total_frames, frame_nr))

        if frame_nr < 0:
            print("No feature data available!")
            return

        for key in f_histdata[frame_nr]:
            f_current[key] = f_histdata[frame_nr][key]

        self.labels["current_frame"].setText("Frame: {}".format(frame_nr + 1))

        label = f_current["label"]
        if action == "frames":
            self.current_frame_data = f_current
            self.graph.update(fdata)
            self.current_sweep = f_current["frame_marker"]
            self.current_frame_nr = frame_nr
            self.textboxes["label"].setText(label)
            self.labels["current_sweep"].setText("Sweep: {}".format(self.current_sweep))
            self.set_slider_value("sweep_slider", self.current_sweep)
            return
        else:
            if self.gui_handle.data is None:
                print("No sweep data available")
                return
            label = self.textboxes["label"].text()

        sweep = number
        sweep_data = self.gui_handle.data

        n_sweeps = len(sweep_data) - f_info["frame_size"] - 2 * f_info["frame_pad"]

        sweep = max(0, sweep)
        sweep = int(min(n_sweeps, sweep))

        frame_start = sweep + 1

        if self.feature_process is None:
            self.feature_process = feature_proc.FeatureProcessing(fdata["sensor_config"])

        self.feature_process.set_feature_list(fdata["ml_frame_data"]["feature_list"])

        fdata = self.feature_process.feature_extraction_window(
            fdata,
            sweep_data,
            frame_start,
            label
            )

        self.current_sweep = sweep

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
            self.update_frame("frames", frame_nr + 1)
        elif "current" in action:
            for key in f_histdata[frame_nr]:
                f_histdata[frame_nr][key] = f_modified[key]
        elif "remove" in action:
            if len(f_histdata) > frame_nr:
                f_histdata.pop(frame_nr)
                self.update_sliders()
                self.update_frame("frames", -1)

    def update_sliders(self):
        if self.gui_handle.data is None or self.gui_handle.ml_data is None:
            return

        nr_sweeps = len(self.gui_handle.data)
        nr_frames = len(self.gui_handle.ml_data["ml_frame_data"]["frame_list"])

        self.sliders["sweep_slider"].set_limits([1, max(nr_sweeps, 1)])
        self.sliders["frame_slider"].set_limits([1, max(nr_frames, 1)])

    def set_slider_value(self, tag, value):
        self.sliders[tag].set_value(value)


class LabelingGraph(QFrame):
    def __init__(self, parent, gui_handle=None):
        super().__init__()

        featproc = feature_proc
        canvas = pg.GraphicsLayoutWidget()
        self.label_graph_widget = featproc.PGUpdater()
        self.label_graph_widget.setup(canvas)

        self.gui_handle = gui_handle
        self.grid = QtWidgets.QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)

        self.grid.addWidget(canvas, 0, 0)

    def update(self, plot_data):
        self.label_graph_widget.update(plot_data)

    def reset_data(self):
        self.label_graph_widget.reset_data()


class TrainingFrame(QFrame):
    def __init__(self, parent, gui_handle=None):
        super().__init__()

        self.grid = QtWidgets.QGridLayout(self)
        self.grid.setContentsMargins(9, 0, 9, 9)

        self.graph = TrainingGraph(self)

        self.color_table = []
        for i in range(101):
            rgb = colorsys.hsv_to_rgb(i / 300., 1.0, 1.0)
            self.color_table.append([round(255*x) for x in rgb])

        self.labels = {
            "input_dimension": QLabel("Feature dimensions: "),
            "data_length": QLabel("0"),
            "with": QLabel(" features with "),
            "xdim": QLabel("0"),
            "times": QLabel(" x "),
            "ydim": QLabel("0"),
            "confusion_matrix": QLabel("Confusion Matrix"),
            "data_info": QLabel("Traning data info"),
        }

        self.labels["confusion_matrix"].setAlignment(QtCore.Qt.AlignHCenter)
        self.labels["data_info"].setAlignment(QtCore.Qt.AlignHCenter)

        self.cm_widget = QTableWidget()
        self.data_widget = QTableWidget()
        self.cm_widget.setMinimumWidth(700)
        self.grid.setColumnStretch(0, 1)

        self.dims = QWidget(self)
        self.dims.grid = QtWidgets.QGridLayout(self.dims)
        self.dims.grid.addWidget(self.labels["data_length"], 0, 0)
        self.dims.grid.addWidget(self.labels["with"], 0, 1)
        self.dims.grid.addWidget(self.labels["ydim"], 0, 2)
        self.dims.grid.addWidget(self.labels["times"], 0, 3)
        self.dims.grid.addWidget(self.labels["xdim"], 0, 4)
        self.dims.grid.setColumnStretch(5, 1)
        self.num = 0
        self.grid.addWidget(self.labels["input_dimension"], self.num, 0)
        self.grid.addWidget(self.dims, self.num, 1)
        self.grid.addWidget(self.graph, self.increment(), 0, 1, 2)
        self.grid.addWidget(QLabel(""), self.increment(), 0, 1, 2)
        self.grid.addWidget(self.labels["confusion_matrix"], self.increment(), 0)
        self.grid.addWidget(self.labels["data_info"], self.num, 1)
        self.grid.addWidget(self.cm_widget, self.increment(), 0)
        self.grid.addWidget(self.data_widget, self.num, 1)

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

        for r in range(row):
            row_sum = np.sum(matrix[r, :])
            for c in range(col):
                percent = matrix[r, c] / row_sum * 100
                entry = "{} ({:.2f}%)".format(matrix[r, c], percent)
                self.cm_widget.setItem(r, c, QTableWidgetItem(entry))
                self.cm_widget.item(r, c).setForeground(QBrush(QtCore.Qt.black))
                color = self.color_table[int(percent)]
                self.cm_widget.item(r, c).setBackground(QColor(*color))
                self.cm_widget.item(r, c).setFlags(QtCore.Qt.ItemIsEnabled)

        self.cm_widget.setHorizontalHeaderLabels(labels)
        self.cm_widget.setVerticalHeaderLabels(labels)

    def update_data_table(self, label_cat, label_list):
        for r in range(self.data_widget.rowCount()):
            for c in range(self.data_widget.columnCount()):
                self.data_widget.removeCellWidget(r, c)
        self.data_widget.setRowCount(0)
        self.data_widget.setColumnCount(0)

        if label_cat is None:
            return

        try:
            label_cat = np.asarray(label_cat)
            label_nums = [int(np.sum(label_cat[:, i])) for i in range(label_cat.shape[1])]
            row = len(label_list)
            col = 1
        except Exception as e:
            print(e)
            return

        self.data_widget.setRowCount(row)
        self.data_widget.setColumnCount(1)

        for r in range(row):
            for c in range(col):
                entry = "{}".format(label_nums[r])
                self.data_widget.setItem(r, c, QTableWidgetItem(entry))
                self.data_widget.item(r, c).setForeground(QBrush(QtCore.Qt.black))
                self.data_widget.item(r, c).setFlags(QtCore.Qt.ItemIsEnabled)
        self.data_widget.setHorizontalHeaderLabels(["Number"])
        self.data_widget.setVerticalHeaderLabels(label_list)

    def show_results(self, plot_data=None, end_result=False, flush_data=False):
        if end_result:
            self.graph.update(plot_data)
        else:
            self.graph.process(plot_data, flush_data)
        return

    def set_feature_dimensions(self, dims):
        self.labels["data_length"].setText(str(dims[0]))
        self.labels["ydim"].setText(str(dims[1]))
        self.labels["xdim"].setText(str(dims[2]))

    def get_feature_dimensions(self):
        return self.textboxes["input_dimension"].text()

    def increment(self):
        self.num += 1
        return self.num


class TrainingSidePanel(QFrame):
    sig_scan = pyqtSignal(str, str, object)

    def __init__(self, parent, gui_handle):
        super().__init__()

        self.train_data = None
        self.test_data = None
        self.eval_mode = None
        self.feature_list = None
        self.train_model_shape = None

        self.gui_handle = gui_handle
        self.keras = self.gui_handle.ml_keras_model = kp.MachineLearning()

        self.grid = QtWidgets.QGridLayout(self)
        self.grid.setContentsMargins(9, 0, 9, 9)

        self.labels = {
            "training": QLabel("Training Settings: "),
            "epochs": QLabel("Epochs: "),
            "batch_size": QLabel("Batch size:"),
            "evaluate": QLabel("Evaluate Settings: "),
            "learning_rate": QLabel("Learning rate:"),
            "delta": QLabel("Min. delta"),
            "patience": QLabel("Patience"),
            "save_load_reset": QLabel("Save/Load/Reset: "),
            "train": QLabel("Train: "),
        }
        self.textboxes = {
            "epochs": QLineEdit("100", self),
            "batch_size": QLineEdit("128", self),
            "split": QLineEdit("0.2", self),
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
        for cb in self.checkboxes:
            self.checkboxes[cb].setEnabled(False)
        self.checkboxes["early_dropout"].setEnabled(True)
        self.checkboxes["early_dropout"].setChecked(True)

        self.buttons = {
            "train": QPushButton("Train", self),
            "stop": QPushButton("Stop", self),
            "load_train_data": QPushButton("Load training data"),
            "load_test_data": QPushButton("Load test data"),
            "save_model": QPushButton("Save model"),
            "clear_model": QPushButton("Clear model"),
            "clear_training": QPushButton("Clear training/test data"),
            "load_model": QPushButton("Load model", self),
        }

        self.buttons["train"].clicked.connect(partial(self.train, "train"))
        self.buttons["stop"].clicked.connect(partial(self.train, "stop"))
        self.buttons["load_train_data"].clicked.connect(self.load_train_data)
        self.buttons["load_test_data"].clicked.connect(self.load_train_data)
        self.buttons["save_model"].clicked.connect(partial(self.model_operation, "save_model"))
        self.buttons["clear_model"].clicked.connect(partial(self.model_operation, "clear_model"))
        self.buttons["clear_training"].clicked.connect(partial(self.model_operation, "clear_data"))
        self.buttons["load_model"].clicked.connect(partial(self.model_operation, "load_model"))

        self.buttons["stop"].setVisible(False)
        self.buttons["train"].setEnabled(False)

        self.drop_down = QComboBox(self)
        self.drop_down.setStyleSheet("background-color: white")
        self.drop_down.setMinimumHeight(25)
        self.drop_down.addItem("Train Accuracy")
        self.drop_down.addItem("Train Loss")
        self.drop_down.addItem("Eval. Accuracy")
        self.drop_down.addItem("Eval. Loss")

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
        self.grid.addWidget(self.labels["training"], self.increment(), 0, 1, 4)
        self.grid.addWidget(QHLine(), self.increment(), 0, 1, 4)
        self.grid.addWidget(self.buttons["load_train_data"], self.increment(), 0, 1, 4)
        self.grid.addWidget(self.buttons["train"], self.increment(), 0, 1, 4)
        self.grid.addWidget(self.buttons["stop"], self.increment(), 0, 1, 4)
        self.grid.addWidget(QLabel(""), self.increment(), 0, 1, 4)
        self.grid.addWidget(self.labels["epochs"], self.increment(), 0, 1, 2)
        self.grid.addWidget(self.textboxes["epochs"], self.num, 2, 1, 2)
        self.grid.addWidget(self.labels["batch_size"], self.increment(), 0, 1, 2)
        self.grid.addWidget(self.textboxes["batch_size"], self.num, 2, 1, 2)
        self.grid.addWidget(self.labels["learning_rate"], self.increment(), 0, 1, 2)
        self.grid.addWidget(self.textboxes["learning_rate"], self.num, 2, 1, 2)
        self.grid.addWidget(QLabel(""), self.increment(), 0, 1, 4)
        self.grid.addWidget(self.checkboxes["early_dropout"], self.increment(), 0, 1, 2)
        self.grid.addWidget(self.drop_down, self.num, 2, 1, 2)
        self.grid.addWidget(self.labels["patience"], self.increment(), 0)
        self.grid.addWidget(self.textboxes["patience"], self.num, 1)
        self.grid.addWidget(self.labels["delta"], self.num, 2)
        self.grid.addWidget(self.textboxes["delta"], self.num, 3)
        self.grid.addWidget(QLabel(""), self.increment(), 0, 1, 4)
        self.grid.addWidget(self.checkboxes["save_best"], self.increment(), 0, 1, 2)
        self.grid.addWidget(QLabel(""), self.increment(), 0, 1, 4)
        self.grid.addWidget(self.radio_frame, self.increment(), 0, 1, 4)
        self.grid.addWidget(QLabel(""), self.increment(), 0, 1, 4)
        self.grid.addWidget(QLabel(""), self.increment(), 0, 1, 4)
        self.grid.addWidget(self.labels["save_load_reset"], self.increment(), 0, 1, 4)
        self.grid.addWidget(QHLine(), self.increment(), 0, 1, 4)
        self.grid.addWidget(self.buttons["save_model"], self.increment(), 0, 1, 4)
        self.grid.addWidget(self.buttons["load_model"], self.increment(), 0, 1, 4)
        self.grid.addWidget(self.buttons["clear_model"], self.increment(), 0, 1, 4)
        self.grid.addWidget(self.buttons["clear_training"], self.increment(), 0, 1, 4)

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

        model_exists = self.gui_handle.eval_sidepanel.model_loaded()

        if filenames:
            try:
                if mode == "training":
                    status = self.keras.load_train_data(filenames, model_exists=model_exists)
                else:
                    status = self.keras.load_test_data(filenames)
            except Exception as e:
                self.gui_handle.error_message("Failed to load {} data:\n {}".format(mode, e))
                return

            if status["success"]:
                if mode == "training":
                    self.train_data = status["data"]
                    self.gui_handle.training.update_data_table(
                        status["data"]["y_labels"],
                        status["data"]["label_list"]
                    )
                else:
                    self.test_data = status["data"]
                self.gui_handle.info_handle(status["message"])
                self.buttons["train"].setEnabled(True)
            else:
                self.gui_handle.error_message(status["message"])
                return

            if mode == "training":
                self.gui_handle.training.set_feature_dimensions(self.train_data["x_data"].shape)
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

    def get_dropout(self):
        if not self.checkboxes["early_dropout"].isChecked():
            return False

        dropout = self.drop_down.currentText()
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

    def train(self, mode):
        if mode == "stop":
            try:
                self.sig_scan.emit("stop", "", "")
            except Exception:
                pass
            self.buttons["stop"].setEnabled(False)
            self.buttons["train"].setEnabled(True)
            return

        if self.train_data is None:
            self.gui_handle.error_message("No training data loaded")
            return
        x = self.train_data["x_data"]
        y = self.train_data["y_labels"]

        save_best = False
        ep = int(self.textboxes["epochs"].text())
        batch = int(self.textboxes["batch_size"].text())
        func = self.gui_handle.training.show_results

        self.buttons["stop"].setEnabled(True)
        self.buttons["train"].setEnabled(False)

        # Todo: Finalize threaded training
        thread_training = False

        if thread_training:
            model_params = {
                "model": self.keras,
                "x": x,
                "y": y,
                "epochs": ep,
                "batch_size": batch,
                "eval_data": self.get_evaluation_mode(),
                "save_best": save_best,
                "dropout": self.get_dropout(),
                "session": self.keras.get_current_session(),
                "graph": self.keras.get_current_graph(),
                "learning_rate": self.get_learning_rate(),
            }
            self.threaded_train = Threaded_Training(model_params, parent=self)
            self.threaded_train.sig_scan.connect(self.thread_receive)
            self.sig_scan.connect(self.threaded_train.receive)
            self.threaded_train.start()
        else:
            self.train_history = self.keras.train(
                x,
                y,
                epochs=ep,
                batch_size=batch,
                eval_data=self.get_evaluation_mode(),
                save_best=save_best,
                dropout=self.get_dropout(),
                learning_rate=self.get_learning_rate(),
                cb_func=func
                )
            self.buttons["stop"].setEnabled(False)
            self.buttons["train"].setEnabled(True)
            try:
                confusion_matrix = self.keras.confusion_matrix(y, self.keras.predict(x))
                self.gui_handle.training.update_confusion_matrix(confusion_matrix)
            except Exception as e:
                print(e)

        side_panel_data = self.gui_handle.eval_sidepanel.model_data
        side_panel_data["feature_list"] = self.train_data["feature_list"]
        side_panel_data["sensor_config"] = self.train_data["sensor_config"]
        side_panel_data["loaded"] = True
        side_panel_data["frame_settings"] = self.train_data["frame_settings"]

        try:
            self.gui_handle.load_gui_settings_from_sensor_config(self.train_data["sensor_config"])
            self.gui_handle.set_sensors(self.train_data["sensor_config"].sensor)
            self.gui_handle.feature_select.update_feature_list(self.train_data["feature_list"])
            self.gui_handle.feature_sidepanel.set_frame_settings(self.train_data["frame_settings"])
        except Exception as e:
            print(e)

    def thread_receive(self, message_type, message, data=None):
        if "training_error" in message_type:
            self.gui_handle.error_message(("{}".format(message)))
            self.buttons["stop"].setEnabled(False)
            self.buttons["train"].setEnabled(True)
        elif message_type == "training_done":
            self.keras.set_current_session(data[1])
            self.buttons["stop"].setEnabled(False)
            self.buttons["train"].setEnabled(True)
            self.keras.confusion_matrix(
                self.train_data["y_labels"],
                self.keras.predict(self.train_data["x_data"])
                )
        elif message_type == "update_plots":
            self.gui_handle.training.show_results(data)
        else:
            print("Thread data not implemented! {}".format(message_type))
            print(message_type, message, data)

    def model_operation(self, op):
        if op == "save_model":
            if not self.gui_handle.eval_sidepanel.model_data["loaded"]:
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
                try:
                    self.keras.save_model(
                        filename,
                        self.train_data["feature_list"],
                        self.train_data["sensor_config"],
                        self.train_data["frame_settings"],
                        )
                except Exception as e:
                    self.gui_handle.error_message("Failed to save model:\n {}".format(e))
                    return
        if op == "clear_model":
            if self.gui_handle.eval_sidepanel.model_loaded():
                self.keras.clear_model(reinit=True)
            self.gui_handle.training.show_results(flush_data=True)
            self.gui_handle.training.update_confusion_matrix(None)
        if op == "clear_data":
            if self.gui_handle.eval_sidepanel.model_loaded():
                self.keras.clear_training_data()
            self.buttons["train"].setEnabled(False)
            self.model_data = None
            self.gui_handle.training.show_results(flush_data=True)
            self.gui_handle.eval_sidepanel.model_data["loaded"] = False
            self.gui_handle.training.update_data_table(None, None)
            self.gui_handle.training.update_confusion_matrix(None)
        if op == "load_model":
            self.gui_handle.eval_sidepanel.load_model()

    def check_vals(self, box):
        success = True
        val = -1
        if box in ["learning_rate", "split", "delta"]:
            try:
                val = float(self.sender().text())
            except Exception:
                pass
            if val <= 0 or val >= 1:
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


class TrainingGraph(QFrame):
    def __init__(self, parent, gui_handle=None):
        super().__init__()

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


class EvalFrame(QFrame):
    def __init__(self, parent, gui_handle=None):
        super().__init__()

        self.feature_process = None
        self.gui_handle = gui_handle
        self.nr_col = 2
        self.model_data = {"loaded": False}

        self.grid = QtWidgets.QGridLayout(self)
        self.grid.setContentsMargins(9, 0, 9, 9)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)

        self.labels = {
            "prediction_label": QLabel("Prediction: "),
            "prediction": QLabel(""),
            "probability_label": QLabel("Probability: "),
            "probability": QLabel(""),
        }
        self.textboxes = {
        }
        for t in self.textboxes:
            self.textboxes[t].setStyleSheet("background-color: white")

        self.checkboxes = {
        }

        self.buttons = {
        }

        self.num = 0
        self.grid.addWidget(QLabel(""), self.num, 0, 1, 2)
        self.grid.addWidget(self.labels["prediction_label"], self.increment(), 0)
        self.grid.addWidget(self.labels["prediction"], self.num, 1)
        self.grid.addWidget(self.labels["probability_label"], self.increment(), 0)
        self.grid.addWidget(self.labels["probability"], self.num, 1)
        self.grid.addWidget(QLabel(""), self.increment(), 0, 1, 2)
        self.grid.addWidget(QHLine(), self.increment(), 0, 1, 2)
        self.grid.addWidget(QLabel(""), self.increment(), 0, 1, 2)

        return

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

        self.grid.addWidget(feature_canvas, self.increment(), 0, 1, self.nr_col)

    def update_prediction(self, prediction):
        self.labels["prediction"].setText(prediction["prediction"])
        self.labels["probability"].setText("{:3.2f}%".format(prediction["confidence"] * 100))

    def increment(self):
        self.num += 1
        return self.num


class EvalSidePanel(QFrame):
    def __init__(self, parent, gui_handle):
        super().__init__()

        self.keras = None

        self.gui_handle = gui_handle
        self.grid = QtWidgets.QGridLayout(self)
        self.grid.setContentsMargins(9, 0, 9, 9)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)
        self.model_data = {"loaded": False}

        self.buttons = {
            "load_model": QPushButton("Load Model", self),
        }

        self.buttons["load_model"].clicked.connect(self.load_model)

        self.num = 0
        self.grid.addWidget(self.buttons["load_model"], self.num, 0, 1, 2)

        self.grid.setRowStretch(self.increment(), 1)

    def increment(self):
        self.num += 1
        return self.num

    def load_model(self):
        if self.keras is None:
            self.keras = self.gui_handle.ml_keras_model
        title = "Load model data"
        options = QtWidgets.QFileDialog.Options()
        options |= QtWidgets.QFileDialog.DontUseNativeDialog
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, title, "", "NumPy data files (*.npy)", options=options)

        if not filename:
            return

        self.model_data = self.keras.load_model(filename)
        if not self.model_data["loaded"]:
            self.gui_handle.error_message(self.model_data["message"])
            return

        d = self.model_data
        try:
            self.gui_handle.load_gui_settings_from_sensor_config(d["sensor_config"])
            self.gui_handle.feature_select.update_feature_list(d["feature_list"])
            self.gui_handle.feature_sidepanel.set_frame_settings(d["frame_settings"])
            self.config_is_valid(show_warning=False)
        except Exception as e:
            self.gui_handle.error_message("Failed to load model data:<br> {}".format(e))
            self.model_data["loaded"] = False
        else:
            self.gui_handle.info_handle(self.model_data["message"])

    def config_is_valid(self, show_warning=True):
        if self.gui_handle.get_gui_state("server_connected"):
            available_sensors = self.gui_handle.get_sensors()
            required_sensors = self.model_data["sensor_config"].sensor
            if len(available_sensors) < len(required_sensors):
                warning = "Sensor missmatch detected!<br>"
                warning += "The model needs {} sensors!<br>Run anyway?".format(
                    len(required_sensors)
                    )
                if show_warning and not self.gui_handle.warning_message(warning):
                    return False
        else:
            self.gui_handle.set_sensors(self.model_data["sensor_config"].sensor)

        try:
            mode = self.model_data["sensor_config"].mode
            if "iq" in mode.lower():
                mode = "IQ"
            elif "envelope" in mode.lower():
                mode = "Envelope"
            else:
                mode = "Sparse"
            if self.gui_handle.module_dd.currentText() != mode:
                warning = "Service missmatch detected!<br>"
                warning += "The model needs {}! Change to correct service?".format(mode)
                if show_warning and not self.gui_handle.warning_message(warning):
                    return False
                index = self.gui_handle.module_dd.findText(mode, QtCore.Qt.MatchFixedString)
                if index >= 0:
                    self.gui_handle.module_dd.setCurrentIndex(index)
                    self.gui_handle.update_canvas()
        except Exception as e:
            print(e)

        return True

    def predict(self, feature_map):
        if self.keras is None:
            self.keras = self.gui_handle.ml_keras_model
        prediction = self.keras.predict(feature_map)[0]
        self.gui_handle.eval_model.update_prediction(prediction)

        return prediction

    def get_feature_list(self):
        if self.model_data["loaded"]:
            return self.model_data["feature_list"]
        else:
            return None

    def get_sensor_config(self):
        if self.model_data["loaded"]:
            return self.model_data["sensor_config"]
        else:
            return None

    def model_loaded(self):
        return self.model_data["loaded"]

    def get_model_shape(self):
        return self.model_data["model_shape"]


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
        self.spin_box.setStyleSheet("background-color: white")
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
        self.spin_box.setValue(value)
        self.slider.setValue(value)

        if self.cb is not None:
            self.cb(self.tag, value)

    def set_value(self, value):
        self.spin_box.setValue(value)
        self.slider.setValue(value)

    def set_limits(self, limits):
        for element in self.box:
            self.box[element].setRange(*limits)

        self.slider_range["start"].setText(str(limits[0]))
        self.slider_range["stop"].setText(str(limits[1]))


class Threaded_Training(QtCore.QThread):
    sig_scan = pyqtSignal(str, str, object)

    def __init__(self, model_data, parent=None):
        QtCore.QThread.__init__(self, parent)

        self.model_data = model_data
        self.model = self.model_data["model"]
        self.epochs = self.model_data["epochs"]

        self.finished.connect(self.stop_thread)

        self.running = True

    def stop_thread(self):
        self.quit()

    def run(self):
        if self.running:
            self.model_data["cb"] = self.update_plots

        epoch = 0
        while self.running and epoch < self.epochs:
            try:
                training_model, session, graph = self.model.threaded_training(self.model_data)
            except Exception as e:
                msg = "Failed to train model!\n{}".format(self.format_error(e))
                self.emit("training_error", msg)
            epoch += 1

        self.emit("training_done", "", [training_model, session, graph])
        self.running = False

    def receive(self, message_type, message, data=None):
        if message_type == "stop":
            self.running = False
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
