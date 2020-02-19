import enum
import os
import sys
from argparse import ArgumentParser
from collections import namedtuple

import numpy as np
import yaml

from PyQt5 import QtCore, QtWidgets
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

import acconeer.exptool


def lib_version_up_to_date(gui_handle=None):
    fdir = os.path.dirname(os.path.realpath(__file__))
    fn = os.path.join(fdir, "../../src/acconeer/exptool/__init__.py")
    if os.path.isfile(fn):
        with open(fn, "r") as f:
            lines = [line.strip() for line in f.readlines()]

        for line in lines:
            if line.startswith("__version__"):
                fs_lib_ver = line.split("=")[1].strip()[1:-1]
                break
        else:
            fs_lib_ver = None
    else:
        fs_lib_ver = None

    used_lib_ver = getattr(acconeer.exptool, "__version__", None)

    rerun_text = "You probably need to reinstall the library (python -m pip install -U --user .)"
    error_text = None
    if used_lib_ver:
        sb_text = "Lib v{}".format(used_lib_ver)

        if fs_lib_ver != used_lib_ver:
            sb_text += " (mismatch)"
            error_text = "Lib version mismatch."
            error_text += " Installed: {} Latest: {}\n".format(used_lib_ver, fs_lib_ver)
            error_text += rerun_text
    else:
        sb_text = "Lib version unknown"
        error_text = "Could not read installed lib version" + rerun_text

    if gui_handle is not None:
        gui_handle.labels["libver"].setText(sb_text)
        if error_text and sys.executable.endswith("pythonw.exe"):
            gui_handle.error_message(error_text)
    else:
        if not sys.executable.endswith("pythonw.exe") and error_text:
            prompt = "\nThe GUI might not work properly!\nContinue anyway? [y/N]"
            while True:
                print(error_text + prompt)
                choice = input().lower()
                if choice.lower() == "y":
                    return True
                elif choice == "" or choice.lower() == "n":
                    return False
                else:
                    sys.stdout.write("Please respond with 'y' or 'n' "
                                     "(or 'Y' or 'N').\n")
        return True


class LoadState(enum.Enum):
    UNLOADED = enum.auto()
    BUFFERED = enum.auto()
    LOADED = enum.auto()


class HandleAdvancedProcessData(QDialog):
    def __init__(self, mode, data_text, parent):
        super().__init__(parent)

        self.mode = mode
        self.data_text = data_text
        self.parent = parent
        self.data = None

        # Examples only supporting loading of advanced data
        loading_only_examples = []

        loading_only = False
        for m in loading_only_examples:
            if m in self.mode.lower():
                loading_only = True

        self.setMinimumWidth(350)
        self.setModal(True)
        self.setWindowTitle("Load advanced process data")

        layout = QVBoxLayout()
        self.setLayout(layout)

        texts = [
            "Load {} specific data from file".format(self.mode),
            "or define data via 'Specify'",
        ]

        for text in texts:
            lbl = QLabel(text, self)
            lbl.setWordWrap(True)
            layout.addWidget(lbl)
            if loading_only:
                break

        layout.addStretch(1)

        if not loading_only:
            self.generate_parameter_inputs(layout)
            layout.addStretch(1)

        buttons_widget = QWidget(self)
        layout.addWidget(buttons_widget)
        hbox = QHBoxLayout()
        buttons_widget.setLayout(hbox)
        hbox.addStretch(1)

        load_btn = QPushButton("Load from file")
        load_btn.setDefault(True)
        load_btn.clicked.connect(self.load)
        hbox.addWidget(load_btn)

        if not loading_only:
            spec_btn = QPushButton("Set parameters")
            spec_btn.clicked.connect(self.get_params)
            hbox.addWidget(spec_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        hbox.addWidget(self.cancel_btn)

    def close_dialog(self):
        self.cancel_btn.click()

    def load(self):
        self.close_dialog()
        options = QtWidgets.QFileDialog.Options()
        options |= QtWidgets.QFileDialog.DontUseNativeDialog
        fname, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Load " + self.data_text, "", "NumPy data Files (*.npy)", options=options
        )
        if fname:
            try:
                self.data = np.load(fname, allow_pickle=True)
            except Exception:
                self.parent.error_message("Failed to load " + self.data_text + "\n")
                self.data = None

    def generate_parameter_inputs(self, layout):
        parameter_wiget = QWidget(self)
        parameter_wiget._grid = QtWidgets.QGridLayout()
        parameter_wiget.setLayout(parameter_wiget._grid)

        self.inputs = None

        if "obstacle" in self.mode.lower():
            self.inputs = [
                [None, None, "Static PWL distance 1"],
                [None, None, "Static PWL distance 2"],
                [None, None, "Static PWL distance 3"],
                [None, None, "Static PWL distance 4"],
                [None, None, "Static PWL distance 5"],
                [None, None, "Static PWL amplitude 1"],
                [None, None, "Static PWL amplitude 2"],
                [None, None, "Static PWL amplitude 3"],
                [None, None, "Static PWL amplitude 4"],
                [None, None, "Static PWL amplitude 5"],
                [None, None, "Moving PWL distance 1"],
                [None, None, "Moving PWL distance 2"],
                [None, None, "Moving PWL amplitude 1"],
                [None, None, "Moving PWL amplitude 2"],
                [None, None, "Static adjacent factor"],
                [None, None, "Moving max"],
            ]
            helper_path = os.path.dirname(os.path.realpath(__file__))
            param_file = os.path.join(
                helper_path,
                "../../examples/processing/obstacle_bg_params_dump.yaml"
            )

        if self.inputs is not None:
            for idx, i in enumerate(self.inputs):
                i[0] = QLabel(i[-1])
                i[1] = QLineEdit("0", self)
                parameter_wiget._grid.addWidget(i[0], idx, 0)
                parameter_wiget._grid.addWidget(i[1], idx, 1)

            try:
                with open(param_file, 'r') as f_handle:
                    params = yaml.full_load(f_handle)
                self.set_params(params)
            except Exception:
                # Continue with empty inputs if file doesn't exist
                print("Failed to set params from file")

        layout.addWidget(parameter_wiget)

    def get_params(self):
        if "obstacle" in self.mode.lower():
            self.data = {
                "static_pwl_dist": [],
                "static_pwl_amp": [],
                "moving_pwl_dist": [],
                "moving_pwl_amp": [],
            }
            for i in self.inputs:
                val = float(i[1].text())
                if "Static PWL distance" in i[-1]:
                    self.data["static_pwl_dist"].append(val)
                elif "Static PWL amplitude" in i[-1]:
                    self.data["static_pwl_amp"].append(val)
                elif "Moving PWL distance" in i[-1]:
                    self.data["moving_pwl_dist"].append(val)
                elif "Moving PWL amplitude" in i[-1]:
                    self.data["moving_pwl_amp"].append(val)
                elif "Static adjacent factor" in i[-1]:
                    self.data["static_adjacent_factor"] = [val]
                elif "Moving max" in i[-1]:
                    self.data["moving_max"] = [val]

        self.close_dialog()

    def set_params(self, params):
        if "obstacle" in self.mode.lower():
            for key in params:
                param = params[key]
                for idx, val in enumerate(param):
                    if key == "static_pwl_dist":
                        input_key = "Static PWL distance {}".format(idx + 1)
                    elif key == "static_pwl_amp":
                        input_key = "Static PWL amplitude {}".format(idx + 1)
                    elif key == "moving_pwl_dist":
                        input_key = "Moving PWL distance {}".format(idx + 1)
                    elif key == "moving_pwl_amp":
                        input_key = "Moving PWL amplitude {}".format(idx + 1)
                    elif key == "static_adjacent_factor":
                        input_key = "Static adjacent factor"
                    elif key == "moving_max":
                        input_key = "Moving max"
                    for entry in self.inputs:
                        if entry[2] == input_key:
                            entry[1].setText(str(val))

    def get_data(self):
        return self.data


class AdvancedSerialDialog(QDialog):
    def __init__(self, state, parent):
        super().__init__(parent)

        self.setMinimumWidth(350)
        self.setModal(True)
        self.setWindowTitle("Advanced serial settings")

        layout = QVBoxLayout()
        self.setLayout(layout)

        texts = [
            "Please note:",
            (
                "Overriding the baud rate disables automatic"
                " detection and negotiation of baud rate."
            ),
            "Only use on special hardware.",
        ]

        for text in texts:
            lbl = QLabel(text, self)
            lbl.setWordWrap(True)
            layout.addWidget(lbl)

        layout.addStretch(1)

        self.cb = QCheckBox("Override baud rate", self)
        self.cb.stateChanged.connect(self.cb_state_changed)
        layout.addWidget(self.cb)

        self.sb = QSpinBox(self)
        self.sb.setRange(1, int(3e6))
        layout.addWidget(self.sb)

        layout.addStretch(1)

        buttons_widget = QWidget(self)
        layout.addWidget(buttons_widget)
        hbox = QHBoxLayout()
        buttons_widget.setLayout(hbox)
        hbox.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        hbox.addWidget(cancel_btn)
        save_btn = QPushButton("Save")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self.accept)
        hbox.addWidget(save_btn)

        self.set_state(state)

    def cb_state_changed(self, state):
        self.sb.setEnabled(bool(state))

    def set_state(self, state):
        checked = state is not None
        self.cb.setChecked(checked)
        self.cb_state_changed(checked)
        self.sb.setValue(state if checked else 115200)

    def get_state(self):
        return self.sb.value() if self.cb.checkState() else None


class GUIArgumentParser(ArgumentParser):
    def __init__(self):
        super().__init__()

        self.add_argument("-ml",
                          "--machine-learning",
                          dest="machine_learning",
                          help="Enable machine learning",
                          action="store_true")

        self.add_argument("-b",
                          "--beta-features",
                          dest="beta_features",
                          help="Enable beta features",
                          action="store_true")


class BiggerMessageBox(QtWidgets.QMessageBox):
    def resizeEvent(self, event):
        result = super().resizeEvent(event)
        self.setFixedWidth(500)
        return result


class Label(QLabel):
    def __init__(self, img, img_scale=0.7):
        super(Label, self).__init__()

        self.img_scale = img_scale
        self.pixmap = QPixmap(img)

        self.setMinimumSize(1, 1)
        self.setAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignHCenter)
        self.setPixmap(self.pixmap)

    def resizeEvent(self, event):
        w = self.size().width() * self.img_scale
        h = self.size().height() * self.img_scale
        scaled_size = QtCore.QSize(w, h)

        scaled_pixmap = self.pixmap.scaled(
            scaled_size,
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation,
        )

        self.setPixmap(scaled_pixmap)


class CollapsibleSection(QFrame):
    def __init__(self, header_text, init_collapsed=False, is_top=False):
        super().__init__()

        if not is_top:
            self.setObjectName("CollapsibleSection")
            self.setStyleSheet("#CollapsibleSection{border-top: 1px solid lightgrey;}")

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self.setLayout(self._layout)
        self._header_widget = QWidget()
        self.body_widget = QWidget()
        self._layout.addWidget(self._header_widget)
        self._layout.addWidget(self.body_widget)

        self.grid = QGridLayout(self.body_widget)
        self.grid.setContentsMargins(9, 0, 9, 9)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)

        self._header_widget_layout = QHBoxLayout(self._header_widget)
        self._header_widget_layout.setContentsMargins(7, 7, 7, 7)
        self._header_widget.setLayout(self._header_widget_layout)

        self._button = QToolButton()
        self._button.setText(header_text)
        self._button.setCheckable(True)
        self._button.setStyleSheet("QToolButton { border: none; }")
        self._button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self._button.pressed.connect(self.button_event)
        self.button_event(override=init_collapsed)
        self._header_widget_layout.addWidget(self._button)
        self._header_widget_layout.addStretch()

    def button_event(self, override=None):
        if override is None:
            checked = not self._button.isChecked()
        else:
            checked = override
            self._button.setChecked(checked)

        if checked:  # collapsed
            self._button.setArrowType(QtCore.Qt.ArrowType.RightArrow)
            self.body_widget.hide()
        else:
            self._button.setArrowType(QtCore.Qt.ArrowType.DownArrow)
            self.body_widget.show()


class SensorSelection(QFrame):
    def __init__(self, multi_sensors=False, error_handler=None, callback=None):
        super().__init__()

        self.error_handler = error_handler
        self.callback = callback

        self.drawing = False
        self.selected = [1]
        self.sources = None
        self.module_multi_sensor_support = multi_sensors

        self.grid = QtWidgets.QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)

        self.checkboxes = []
        self.radio_buttons = []
        for i in range(4):
            s = i + 1

            cb = QCheckBox(str(s), self)
            cb.stateChanged.connect(lambda val, cb=cb: self.checkbox_event_handler(val, cb))
            self.checkboxes.append(cb)
            self.grid.addWidget(cb, 0, i)

            rb = QtWidgets.QRadioButton(str(s), self)
            rb.toggled.connect(lambda val, rb=rb: self.radio_button_event_handler(val, rb))
            self.radio_buttons.append(rb)
            self.grid.addWidget(rb, 1, i)

        self.draw()

    def checkbox_event_handler(self, state, cb):
        if self.drawing:
            return

        s = int(cb.text())

        if state:  # checked
            if s not in self.selected:
                self.selected.insert(0, s)
        else:
            if s in self.selected:
                self.selected.remove(s)

        self.draw()

    def radio_button_event_handler(self, selected, rb):
        if self.drawing or not selected:
            return

        s = int(rb.text())
        self.selected = [s]
        self.draw()

    def draw(self):
        self.drawing = True

        for i, (cb, rb) in enumerate(zip(self.checkboxes, self.radio_buttons)):
            s = i + 1

            if self.sources:
                enabled = s in self.sources
            else:
                enabled = True

            cb.setEnabled(enabled)
            rb.setEnabled(enabled)

            cb.setVisible(bool(self.module_multi_sensor_support))
            rb.setVisible(not bool(self.module_multi_sensor_support))

        for i, cb in enumerate(self.checkboxes):
            s = i + 1
            cb.setChecked(s in self.selected)
            rb.setChecked(False)

        if self.selected:
            self.radio_buttons[self.selected[0] - 1].setChecked(True)

        self.drawing = False

        if self.callback is not None:
            self.callback()

    def sanitize(self):
        if self.sources:
            self.selected = [s for s in self.selected if s in self.sources]

        if self.module_multi_sensor_support:
            if isinstance(self.module_multi_sensor_support, list):
                lim = self.module_multi_sensor_support[1]
                self.selected = self.selected[: lim]
        else:
            if self.selected:
                self.selected = [self.selected[0]]

    def get_sensors(self):
        return list(sorted(self.selected))

    def set_sensors(self, sensors):
        self.selected = sensors
        self.sanitize()
        self.draw()

    def set_multi_sensor_support(self, sources, module_multi_sensor_support):
        self.sources = sources
        self.module_multi_sensor_support = module_multi_sensor_support
        self.sanitize()
        self.draw()


class SessionInfoView(QWidget):
    Field = namedtuple("Field", ["label", "unit", "fmt_str", "get_fun"])

    FIELDS = [
        Field("Actual range start", "m", "{:.3f}", lambda d: d["range_start_m"]),
        Field("Actual range length", "m", "{:.3f}", lambda d: d["range_length_m"]),
        Field(
            "Actual range end",
            "m",
            "{:.3f}",
            lambda d: d["range_start_m"] + d["range_length_m"],
        ),
        Field("Step length", "mm", "{:.2f}", lambda d: d["step_length_m"] * 1e3),
        Field("Number of data points", "", "{}", lambda d: d["data_length"]),
        Field("Sweep rate", "Hz", "{:.0f}", lambda d: d["sweep_rate"]),
        Field("Stitch count", "", "{}", lambda d: d["stitch_count"]),
        Field("Depth LPF cutoff ratio", "", "{:.6f}", lambda d: d["depth_lowpass_cutoff_ratio"]),
    ]

    def __init__(self, parent):
        super().__init__(parent)

        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        self.setLayout(grid)

        self.field_widgets = []
        for i, field in enumerate(self.FIELDS):
            key_lbl = QLabel(field.label, self)
            val_lbl = QLabel("", self)
            unit_lbl = QLabel(field.unit, self)
            grid.addWidget(key_lbl, i, 0)
            grid.addWidget(val_lbl, i, 1, QtCore.Qt.AlignRight)
            grid.addWidget(unit_lbl, i, 2)
            self.field_widgets.append((key_lbl, val_lbl, unit_lbl))

        self.no_info_lbl = QLabel("No active or buffered session", self)
        grid.addWidget(self.no_info_lbl, i + 1, 0, 1, 3)

        self.update()

    def update(self, info=None):
        self.no_info_lbl.setVisible(not info)

        for field, widgets in zip(self.FIELDS, self.field_widgets):
            try:
                val = field.get_fun(info)
                text = field.fmt_str.format(val)
            except Exception:
                text = None

            for w in widgets:
                w.setVisible(bool(text))

            widgets[1].setText(str(text))


class ErrorFormater:
    def __init__(self):
        pass

    def error_to_text(self, error):
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        err_text = "File: {}<br>Line: {}<br>Error: {}".format(fname, exc_tb.tb_lineno, error)

        return err_text


class QHLine(QFrame):
    def __init__(self):
        super(QHLine, self).__init__()
        self.setFrameShape(QFrame.HLine)
        self.setFrameShadow(QFrame.Sunken)


class QVLine(QFrame):
    def __init__(self):
        super(QVLine, self).__init__()
        self.setFrameShape(QFrame.VLine)
        self.setFrameShadow(QFrame.Sunken)


class PassthroughProcessor:
    def __init__(self, sensor_config, processing_config, session_info):
        pass

    def process(self, data):
        return data


class Count:
    def __init__(self, val=0):
        self.val = val

    def pre_incr(self):
        self.val += 1
        return self.val

    def post_incr(self):
        ret = self.val
        self.val += 1
        return ret

    def decr(self, val=1):
        self.val -= val

    def set_val(self, val):
        self.val = val
