# Copyright (c) Acconeer AB, 2022
# All rights reserved

import numpy as np

from PySide6 import QtCore
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from . import configbase


cb = configbase  # Workaround for Python 3.6 issue 30024


def _limits_for_qt(set_limits):
    limits = [-1e9, 1e9]

    if set_limits is not None:
        for i in range(2):
            if set_limits[i] is not None:
                limits[i] = set_limits[i]

    return limits


def try_rst_to_html(s):
    try:
        return rst_to_html(s)
    except Exception:
        return s


def rst_to_html(s):
    import re

    from docutils.core import publish_parts

    s = re.sub(r":ref:`([\s\S]+?)\s*<([\s\S]+)>`", r"\1", s, re.MULTILINE)
    parts = publish_parts(s, writer_name="html")
    return parts["body"]


def wrap_qwidget(cls):
    class QWidgetWrapper(cls):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)

        def wheelEvent(self, event):
            if self.hasFocus():
                super().wheelEvent(event)
            else:
                event.ignore()

    return QWidgetWrapper


class Pidget(QFrame):
    def __init__(self, param, parent_instance):
        super().__init__()

        self.param = param
        self._parent_instance = parent_instance

        self._enable_event_handler = False

        self.hide()

    def update(self, alerts=None):
        self._enable_event_handler = False
        self._update(alerts)
        self._enable_event_handler = True

    def _update(self, *args, **kwargs):
        pass

    def _get_param_value(self):
        return self.param.__get__(self._parent_instance)

    def _subwidget_event_handler(self, val):
        if self._enable_event_handler:
            self.param.pidget_event_handler(self._parent_instance, val)


class PidgetStub(Pidget):
    def __init__(self, param, parent_instance):
        super().__init__(param, parent_instance)

        self.setObjectName("frame")
        self.default_css = "#frame {border: 1px solid lightgrey; border-radius: 3px;}"
        self.setStyleSheet(self.default_css)

        doc = param.generate_doc()
        if doc:
            doc = try_rst_to_html(doc)
            self.setToolTip(doc)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 6, 0, 6)

        self.grid_widget = QWidget()
        self.layout.addWidget(self.grid_widget)

        self.grid = QGridLayout(self.grid_widget)
        self.grid.setContentsMargins(6, 0, 6, 0)

        self.alert_frame = QFrame()
        self.alert_frame.setStyleSheet(".QFrame {border-top: 1px solid lightgrey;}")
        alert_layout = QHBoxLayout(self.alert_frame)
        alert_layout.setContentsMargins(6, 6, 6, 0)
        self.alert_label = QLabel()
        self.alert_label.setStyleSheet("color: #333333; font-weight: 600;")
        alert_layout.addWidget(self.alert_label)
        self.layout.addWidget(self.alert_frame)
        self._set_alert(None)

    def _update(self, alerts):
        state = self._parent_instance._state

        if state != cb.Config.State.UNLOADED:
            if callable(self.param.visible):
                visible = self.param.visible(self._parent_instance)
            else:
                visible = self.param.visible
        else:
            visible = False

        self.setVisible(bool(visible))

        enabled = (
            state == cb.Config.State.LOADED
            or state == cb.Config.State.LIVE
            and self.param.is_live_updateable
        )
        enabled = enabled and self.param.enabled
        self.setEnabled(enabled)

        self._set_alert(alerts)

    def _set_alert(self, alerts):
        if not alerts:
            self.alert_frame.hide()
            self.setStyleSheet(self.default_css)
            return

        if isinstance(alerts, cb.Alert):
            alert = alerts
        else:
            alerts = sorted(alerts, key=lambda a: a.severity)
            alert = alerts[0]

        if alert.severity == cb.Severity.ERROR:
            bg = "FFB9A8"
        elif alert.severity == cb.Severity.WARNING:
            bg = "FFDFA8"
        else:
            bg = "FFFFEE"

        self.setStyleSheet(
            (
                "#frame {{"
                "background-color: #{};"
                "border: 1px solid lightgrey;"
                "border-radius: 3px;"
                "}}"
            ).format(bg)
        )
        self.alert_label.setText(alert.msg)
        self.alert_frame.show()

    def _subwidget_event_handler(self, val):
        try:
            super()._subwidget_event_handler(val)
        except ValueError:
            pass  # TODO


class ComboBoxPidget(PidgetStub):
    def __init__(self, param, parent_instance):
        assert isinstance(param, cb.EnumParameter)

        super().__init__(param, parent_instance)

        label = QLabel(param.label, self)
        self.grid.addWidget(label, 0, 0, 1, 1)

        self.cb = wrap_qwidget(QComboBox)()
        members = param.enum.__members__.values()
        label_attrib_name = "label" if hasattr(param.enum, "label") else "value"
        self.cb.addItems([getattr(e, label_attrib_name) for e in members])
        self.cb.currentIndexChanged.connect(self.__cb_event_handler)
        self.grid.addWidget(self.cb, 0, 1, 1, 1)

        self.update()

    def _update(self, *args, **kwargs):
        super()._update(*args, **kwargs)
        value = self._get_param_value()
        index = list(self.param.enum.__members__.values()).index(value)
        self.cb.setCurrentIndex(index)

    def __cb_event_handler(self, index):
        value = list(self.param.enum.__members__.values())[index]
        self._subwidget_event_handler(value)


class IntComboBoxPidget(PidgetStub):
    def __init__(self, param, parent_instance):
        assert isinstance(param, cb.IntParameter)

        super().__init__(param, parent_instance)

        label = QLabel(param.label, self)
        self.grid.addWidget(label, 0, 0, 1, 1)

        self.cb = wrap_qwidget(QComboBox)()
        members = param.valid_values
        self.cb.addItems([str(e) for e in members])
        self.cb.currentIndexChanged.connect(self.__cb_event_handler)
        self.grid.addWidget(self.cb, 0, 1, 1, 1)

        self.update()

    def _update(self, *args, **kwargs):
        super()._update(*args, **kwargs)
        value = self._get_param_value()
        index = self.param.valid_values.index(value)
        self.cb.setCurrentIndex(index)

    def __cb_event_handler(self, index):
        value = self.param.valid_values[index]
        self._subwidget_event_handler(value)


class BoolCheckboxPidget(PidgetStub):
    def __init__(self, param, parent_instance):
        super().__init__(param, parent_instance)

        self.checkbox = QCheckBox(param.label, self)
        self.checkbox.setTristate(False)
        self.checkbox.stateChanged.connect(self._subwidget_event_handler)
        self.grid.addWidget(self.checkbox, 0, 0, 1, 1)

        self.update()

    def _update(self, *args, **kwargs):
        super()._update(*args, **kwargs)
        value = self._get_param_value()
        self.checkbox.setChecked(value)


class IntSpinBoxPidget(PidgetStub):
    def __init__(self, param, parent_instance):
        assert isinstance(param, cb.IntParameter)

        super().__init__(param, parent_instance)

        self.grid.setColumnStretch(0, 7)
        self.grid.setColumnStretch(1, 3)

        label = QLabel(self)
        suffix = " [{}]".format(param.unit) if param.unit else ""
        label.setText(param.label + suffix)
        self.grid.addWidget(label, 0, 0, 1, 1)

        self.spin_box = wrap_qwidget(QSpinBox)(self)
        self.spin_box.setSingleStep(param.step)
        self.spin_box.setKeyboardTracking(False)
        self.spin_box.setRange(*(int(round(x)) for x in _limits_for_qt(param.limits)))

        if param.is_optional:
            self.checkbox = QCheckBox(param.optional_label, self)
            self.checkbox.setTristate(False)
            self.checkbox.stateChanged.connect(self.__checkbox_event_handler)

            self.grid.setColumnStretch(1, 1)
            self.grid.addWidget(self.checkbox, 0, 1, 1, 1)

            self.grid.setColumnStretch(2, 1)
            self.grid.addWidget(self.spin_box, 0, 2, 1, 1)

            self.spin_box.setValue(self.param.optional_default_set_value)
        else:
            self.checkbox = None
            self.grid.addWidget(self.spin_box, 0, 1, 1, 1)

        self.spin_box.valueChanged.connect(self.__spin_box_event_handler)

        self.update()

    def _update(self, *args, **kwargs):
        super()._update(*args, **kwargs)
        value = self._get_param_value()
        is_set = value is not None

        if is_set:
            self.spin_box.setValue(value)

        self.spin_box.setEnabled(is_set)

        if self.checkbox is not None:
            self.checkbox.setChecked(is_set)

    def __checkbox_event_handler(self, val):
        if val:
            val = self.spin_box.value()
        else:
            val = None

        self._subwidget_event_handler(val)

    def __spin_box_event_handler(self, val):
        if self.param.is_optional:
            if not self.checkbox.isChecked():
                val = None

        self._subwidget_event_handler(val)


class FloatRangeSpinBoxesPidget(PidgetStub):
    def __init__(self, param, parent_instance):
        assert isinstance(param, cb.FloatRangeParameter)

        super().__init__(param, parent_instance)

        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)

        label = QLabel(self)
        suffix = " [{}]".format(param.unit) if param.unit else ""
        label.setText(param.label + suffix)
        self.grid.addWidget(label, 0, 0, 1, 1)

        self.spin_boxes = []
        for i in range(2):
            spin_box = wrap_qwidget(QDoubleSpinBox)(self)
            spin_box.setDecimals(param.decimals)
            spin_box.setSingleStep(10 ** (-param.decimals))
            spin_box.valueChanged.connect(lambda v, i=i: self.__spin_box_event_handler(v, i))
            spin_box.setKeyboardTracking(False)
            spin_box.setRange(*_limits_for_qt(param.limits))
            self.grid.addWidget(spin_box, 1, i, 1, 1)
            self.spin_boxes.append(spin_box)

        self.update()

    def _update(self, *args, **kwargs):
        super()._update(*args, **kwargs)
        values = self._get_param_value()

        for spin_box, val in zip(self.spin_boxes, values):
            spin_box.setValue(val)

    def __spin_box_event_handler(self, val, index):
        vals = self._get_param_value()
        vals[index] = val
        self._subwidget_event_handler(vals)


class FloatSpinBoxPidget(PidgetStub):
    def __init__(self, param, parent_instance):
        assert isinstance(param, cb.FloatParameter)

        super().__init__(param, parent_instance)

        self.grid.setColumnStretch(0, 7)
        self.grid.setColumnStretch(1, 3)

        label = QLabel(self)
        suffix = " [{}]".format(param.unit) if param.unit else ""
        label.setText(param.label + suffix)
        self.grid.addWidget(label, 0, 0, 1, 1)

        self.spin_box = wrap_qwidget(QDoubleSpinBox)(self)
        self.spin_box.setDecimals(param.decimals)
        self.spin_box.setSingleStep(10 ** (-param.decimals))
        self.spin_box.setKeyboardTracking(False)
        self.spin_box.setRange(*_limits_for_qt(param.limits))

        if param.is_optional:
            self.checkbox = QCheckBox(param.optional_label, self)
            self.checkbox.setTristate(False)
            self.checkbox.stateChanged.connect(self.__checkbox_event_handler)

            self.grid.setColumnStretch(1, 1)
            self.grid.addWidget(self.checkbox, 0, 1, 1, 1)

            self.grid.setColumnStretch(2, 1)
            self.grid.addWidget(self.spin_box, 0, 2, 1, 1)

            self.spin_box.setValue(self.param.optional_default_set_value)
        else:
            self.checkbox = None
            self.grid.addWidget(self.spin_box, 0, 1, 1, 1)

        self.spin_box.valueChanged.connect(self.__spin_box_event_handler)

        self.update()

    def _update(self, *args, **kwargs):
        super()._update(*args, **kwargs)
        value = self._get_param_value()
        is_set = value is not None

        if is_set:
            self.spin_box.setValue(value)

        self.spin_box.setEnabled(is_set)

        if self.checkbox is not None:
            self.checkbox.setChecked(is_set)

    def __checkbox_event_handler(self, val):
        if val:
            val = self.spin_box.value()
        else:
            val = None

        self._subwidget_event_handler(val)

    def __spin_box_event_handler(self, val):
        if self.param.is_optional:
            if not self.checkbox.isChecked():
                val = None

        self._subwidget_event_handler(val)


class FloatSpinBoxAndSliderPidget(PidgetStub):
    NUM_SLIDER_STEPS = 200

    def __init__(self, param, parent_instance):
        assert isinstance(param, cb.FloatParameter)

        super().__init__(param, parent_instance)

        self.grid.setColumnStretch(0, 7)
        self.grid.setColumnStretch(1, 3)

        label = QLabel(self)
        suffix = " [{}]".format(param.unit) if param.unit else ""
        label.setText(param.label + suffix)
        self.grid.addWidget(label, 0, 0, 1, 1)

        self.spin_box = wrap_qwidget(QDoubleSpinBox)(self)
        self.spin_box.setDecimals(param.decimals)
        self.spin_box.setSingleStep(10 ** (-param.decimals))
        self.spin_box.valueChanged.connect(self._subwidget_event_handler)
        self.spin_box.setKeyboardTracking(False)
        self.spin_box.setRange(*_limits_for_qt(param.limits))
        self.grid.addWidget(self.spin_box, 0, 1, 1, 1)

        slider_widget = QWidget()
        slider_layout = QHBoxLayout(slider_widget)
        slider_layout.setContentsMargins(0, 0, 0, 0)
        slider_layout.addWidget(QLabel(str(param.limits[0])))
        self.slider = wrap_qwidget(QSlider)(QtCore.Qt.Horizontal)
        self.slider.setRange(0, self.NUM_SLIDER_STEPS)
        self.slider.sliderPressed.connect(self.__slider_event_handler)
        self.slider.valueChanged.connect(self.__slider_event_handler)
        slider_layout.addWidget(self.slider, 1)
        slider_layout.addWidget(QLabel(str(param.limits[1])))
        self.grid.addWidget(slider_widget, 1, 0, 1, 2)

        self.update()

    def _update(self, *args, **kwargs):
        super()._update(*args, **kwargs)
        value = self._get_param_value()
        self.spin_box.setValue(value)
        self.slider.setValue(self.__to_slider_scale(value))

    def __slider_event_handler(self, x=None):
        if x is None:
            x = self.slider.sliderPosition()

        self._subwidget_event_handler(self.__from_slider_scale(x))

    def __to_slider_scale(self, x):
        lower, upper = self.param.limits

        if self.param.logscale:
            lower = np.log(lower)
            upper = np.log(upper)
            x = np.log(x)

        y = (x - lower) / (upper - lower) * self.NUM_SLIDER_STEPS
        return int(round(y))

    def __from_slider_scale(self, y):
        lower, upper = self.param.limits

        if self.param.logscale:
            lower = np.log(lower)
            upper = np.log(upper)

        x = y / self.NUM_SLIDER_STEPS * (upper - lower) + lower

        if self.param.logscale:
            x = np.exp(x)

        return x
