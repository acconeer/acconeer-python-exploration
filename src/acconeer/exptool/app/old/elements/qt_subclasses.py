# Copyright (c) Acconeer AB, 2022
# All rights reserved

from collections import namedtuple

from PySide6 import QtCore, QtWidgets
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


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
        w = int(round(self.size().width() * self.img_scale))
        h = int(round(self.size().height() * self.img_scale))
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
                self.selected = self.selected[:lim]
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
