# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import abc
from enum import Enum
from typing import Any, Generic, Optional, Tuple, Type, TypeVar

import attrs
import numpy as np

from PySide6 import QtCore, QtGui
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from acconeer.exptool.a121._core.entities import Criticality


def widget_wrap_layout(layout: QLayout) -> QWidget:
    dummy = QWidget()
    dummy.setLayout(layout)
    return dummy


T = TypeVar("T")
EnumT = TypeVar("EnumT", bound=Enum)


@attrs.frozen(kw_only=True, slots=False)
class ParameterWidgetFactory(abc.ABC):
    name_label_text: str
    name_label_tooltip: Optional[str] = None
    note_label_text: Optional[str] = None

    @abc.abstractmethod
    def create(self, parent: QWidget) -> ParameterWidget:
        ...


class ParameterWidget(QWidget):
    """Base class for a parameter-bound widget.

    A ``ParameterWidget`` comes with a
    ``name`` label and an ``note`` label by default.
    """

    sig_parameter_changed = QtCore.Signal(object)

    def __init__(self, factory: ParameterWidgetFactory, parent: QWidget) -> None:
        super().__init__(parent=parent)

        self.setLayout(QVBoxLayout(self))
        self.layout().setContentsMargins(0, 0, 0, 0)

        self._body_widget = QWidget(self)
        self.layout().addWidget(self._body_widget)

        self.__label_widget = QLabel(factory.name_label_text, parent=self._body_widget)
        if factory.name_label_tooltip is not None:
            self.__label_widget.setToolTip(factory.name_label_tooltip)

        self._body_layout = self._create_body_layout(self.__label_widget)
        self._body_widget.setLayout(self._body_layout)

        self.__note_widget = QLabel(parent=self)
        self.__note_widget.setWordWrap(True)
        self.__note_widget.setContentsMargins(5, 5, 5, 5)
        self.set_note_text(factory.note_label_text)
        self.layout().addWidget(self.__note_widget)

    def _create_body_layout(self, note_label_widget: QWidget) -> QLayout:
        """Called by ParameterWidget.__init__"""

        layout = QHBoxLayout(self._body_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(note_label_widget)
        return layout

    def set_note_text(
        self, message: Optional[str], criticality: Optional[Criticality] = None
    ) -> None:
        if not message:
            self.__note_widget.hide()
            return

        COLOR_MAP = {
            Criticality.ERROR: "#E6635A",
            Criticality.WARNING: "#FCC842",
            None: "white",
        }

        self.__note_widget.show()
        self.__note_widget.setText(message)
        self.__note_widget.setStyleSheet(
            f"background-color: {COLOR_MAP[criticality]}; color: white; font: bold italic;"
        )

    @abc.abstractmethod
    def set_parameter(self, value: Any) -> None:
        pass


@attrs.frozen(kw_only=True, slots=False)
class IntParameterWidgetFactory(ParameterWidgetFactory):
    limits: Optional[Tuple[Optional[int], Optional[int]]] = None
    suffix: Optional[str] = None

    def create(self, parent: QWidget) -> IntParameterWidget:
        return IntParameterWidget(self, parent)


class IntParameterWidget(ParameterWidget):
    def __init__(self, factory: IntParameterWidgetFactory, parent: QWidget) -> None:
        super().__init__(factory, parent)

        self.__spin_box = _PidgetSpinBox(
            self._body_widget,
            limits=factory.limits,
            suffix=factory.suffix,
        )
        self.__spin_box.valueChanged.connect(self.__on_changed)
        self._body_layout.addWidget(self.__spin_box)

    def set_parameter(self, value: Any) -> None:
        assert isinstance(value, int)

        with QtCore.QSignalBlocker(self):
            self.__spin_box.setValue(value)

    def __on_changed(self) -> None:
        self.sig_parameter_changed.emit(self.__spin_box.value())


@attrs.frozen(kw_only=True, slots=False)
class FloatParameterWidgetFactory(ParameterWidgetFactory):
    limits: Optional[Tuple[Optional[float], Optional[float]]] = None
    suffix: Optional[str] = None
    decimals: int = 1

    def create(self, parent: QWidget) -> FloatParameterWidget:
        return FloatParameterWidget(self, parent)


class FloatParameterWidget(ParameterWidget):
    def __init__(self, factory: FloatParameterWidgetFactory, parent: QWidget) -> None:
        super().__init__(factory, parent)

        self.__spin_box = _PidgetDoubleSpinBox(
            self._body_widget,
            limits=factory.limits,
            suffix=factory.suffix,
            decimals=factory.decimals,
        )
        self.__spin_box.valueChanged.connect(self.__on_changed)
        self._body_layout.addWidget(self.__spin_box)

    def set_parameter(self, value: Any) -> None:
        assert isinstance(value, (int, float))

        with QtCore.QSignalBlocker(self):
            self.__spin_box.setValue(value)

    def __on_changed(self) -> None:
        self.sig_parameter_changed.emit(self.__spin_box.value())


@attrs.frozen(kw_only=True, slots=False)
class FloatSliderParameterWidgetFactory(FloatParameterWidgetFactory):
    limits: Tuple[float, float]
    log_scale: bool = False
    show_limit_values: bool = True
    limit_texts: Optional[Tuple[Optional[str], Optional[str]]] = None

    def __attrs_post_init__(self) -> None:
        if self.log_scale:
            if self.limits[0] <= 0:
                raise ValueError("Lower limit must be > 0 when using log scale")

    def create(self, parent: QWidget) -> FloatSliderParameterWidget:
        return FloatSliderParameterWidget(self, parent)


class FloatSliderParameterWidget(ParameterWidget):
    def __init__(self, factory: FloatSliderParameterWidgetFactory, parent: QWidget) -> None:
        super().__init__(factory, parent)

        self.__spin_box = _PidgetDoubleSpinBox(
            self._body_widget,
            limits=factory.limits,
            suffix=factory.suffix,
            decimals=factory.decimals,
        )
        self.__spin_box.valueChanged.connect(self.__on_spin_box_changed)
        self._body_layout.addWidget(self.__spin_box, 0, 1)

        slider_widget = QWidget(self._body_widget)
        self._body_layout.addWidget(slider_widget, 1, 0, 1, -1)
        slider_widget.setLayout(QHBoxLayout(slider_widget))
        slider_widget.layout().setContentsMargins(11, 6, 11, 0)

        lower_limit, upper_limit = factory.limits
        if factory.show_limit_values:
            slider_widget.layout().addWidget(QLabel(str(lower_limit), slider_widget))

        self.__slider = _PidgetFloatSlider(
            slider_widget,
            limits=factory.limits,
            decimals=factory.decimals,
            log_scale=factory.log_scale,
        )
        self.__slider.wrapped_value_changed.connect(self.__on_slider_changed)
        slider_widget.layout().addWidget(self.__slider)

        if factory.show_limit_values:
            slider_widget.layout().addWidget(QLabel(str(upper_limit), slider_widget))

        if factory.limit_texts is not None:
            label_text_widget = QWidget(self._body_widget)
            self._body_layout.addWidget(label_text_widget, 2, 0, 1, -1)
            label_text_widget.setLayout(QHBoxLayout(label_text_widget))
            label_text_widget.layout().setContentsMargins(11, 0, 11, 0)
            label_text_widget.layout().setSpacing(0)

            left, right = factory.limit_texts

            if left is not None:
                label = QLabel(left, label_text_widget)
                label_text_widget.layout().addWidget(label)

            label_text_widget.layout().addStretch(1)

            if right is not None:
                label = QLabel(right, label_text_widget)
                label_text_widget.layout().addWidget(label)

    def _create_body_layout(self, note_label_widget: QWidget) -> QLayout:
        """Called by ParameterWidget.__init__"""

        layout = QGridLayout(self._body_widget)
        layout.setContentsMargins(0, 0, 0, 6)
        layout.setSpacing(0)
        layout.addWidget(note_label_widget, 0, 0)
        return layout

    def set_parameter(self, value: Any) -> None:
        assert isinstance(value, (int, float))

        with QtCore.QSignalBlocker(self):
            self.__spin_box.setValue(value)
            self.__slider.wrapped_set_value(value)

    def __on_spin_box_changed(self, value: float) -> None:
        with QtCore.QSignalBlocker(self):
            self.__slider.wrapped_set_value(value)

        self.sig_parameter_changed.emit(value)

    def __on_slider_changed(self, value: float) -> None:
        with QtCore.QSignalBlocker(self):
            self.__spin_box.setValue(value)

        self.sig_parameter_changed.emit(value)


@attrs.frozen(kw_only=True, slots=False)
class OptionalParameterWidgetFactory(ParameterWidgetFactory):
    checkbox_label_text: Optional[str] = None


class OptionalParameterWidget(ParameterWidget):
    """Optional parameter, not optional widget"""

    def __init__(self, factory: OptionalParameterWidgetFactory, parent: QWidget) -> None:
        super().__init__(factory, parent)

        self._optional_widget = QWidget(self._body_widget)
        self._body_layout.addWidget(self._optional_widget)

        self._none_checkbox = QCheckBox(self._optional_widget)
        if factory.checkbox_label_text:
            self._none_checkbox.setText(factory.checkbox_label_text)

        self._optional_layout = self._create_optional_layout(self._none_checkbox)

    def _create_optional_layout(self, none_checkbox: QWidget) -> QLayout:
        """Called by OptionalParameterWidget.__init__"""

        layout = QHBoxLayout(self._optional_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch(1)
        layout.addWidget(none_checkbox)
        return layout

    def set_parameter(self, value: Any) -> None:
        with QtCore.QSignalBlocker(self):
            self._none_checkbox.setChecked(value is not None)


@attrs.frozen(kw_only=True, slots=False)
class OptionalIntParameterWidgetFactory(OptionalParameterWidgetFactory, IntParameterWidgetFactory):
    init_set_value: Optional[int] = None

    def create(self, parent: QWidget) -> OptionalIntParameterWidget:
        return OptionalIntParameterWidget(self, parent)


class OptionalIntParameterWidget(OptionalParameterWidget):
    def __init__(self, factory: OptionalIntParameterWidgetFactory, parent: QWidget) -> None:
        super().__init__(factory, parent)

        self.__spin_box = _PidgetSpinBox(
            self._optional_widget,
            limits=factory.limits,
            suffix=factory.suffix,
            init_set_value=factory.init_set_value,
        )
        self._optional_layout.addWidget(self.__spin_box)

        self._none_checkbox.stateChanged.connect(self.__on_changed)
        self.__spin_box.valueChanged.connect(self.__on_changed)

    def __on_changed(self) -> None:
        checked = self._none_checkbox.isChecked()

        with QtCore.QSignalBlocker(self):
            self.__spin_box.setEnabled(checked)

        value = self.__spin_box.value() if checked else None
        self.sig_parameter_changed.emit(value)

    def set_parameter(self, value: Any) -> None:
        super().set_parameter(value)

        with QtCore.QSignalBlocker(self):
            if value is None:
                self.__spin_box.setEnabled(False)
            else:
                self.__spin_box.setValue(value)
                self.__spin_box.setEnabled(True)


@attrs.frozen(kw_only=True, slots=False)
class OptionalFloatParameterWidgetFactory(
    OptionalParameterWidgetFactory, FloatParameterWidgetFactory
):
    init_set_value: Optional[float] = None

    def create(self, parent: QWidget) -> OptionalFloatParameterWidget:
        return OptionalFloatParameterWidget(self, parent)


class OptionalFloatParameterWidget(OptionalParameterWidget):
    def __init__(self, factory: OptionalFloatParameterWidgetFactory, parent: QWidget) -> None:
        super().__init__(factory, parent)

        self.__spin_box = _PidgetDoubleSpinBox(
            self._optional_widget,
            decimals=factory.decimals,
            limits=factory.limits,
            suffix=factory.suffix,
            init_set_value=factory.init_set_value,
        )
        self._optional_layout.addWidget(self.__spin_box)

        self._none_checkbox.stateChanged.connect(self.__on_changed)
        self.__spin_box.valueChanged.connect(self.__on_changed)

    def __on_changed(self) -> None:
        checked = self._none_checkbox.isChecked()

        with QtCore.QSignalBlocker(self):
            self.__spin_box.setEnabled(checked)

        value = self.__spin_box.value() if checked else None
        self.sig_parameter_changed.emit(value)

    def set_parameter(self, value: Any) -> None:
        super().set_parameter(value)

        with QtCore.QSignalBlocker(self):
            if value is None:
                self.__spin_box.setEnabled(False)
            else:
                self.__spin_box.setValue(value)
                self.__spin_box.setEnabled(True)


@attrs.frozen(kw_only=True, slots=False)
class CheckboxParameterWidgetFactory(ParameterWidgetFactory):
    def create(self, parent: QWidget) -> CheckboxParameterWidget:
        return CheckboxParameterWidget(self, parent)


class CheckboxParameterWidget(ParameterWidget):
    def __init__(self, factory: CheckboxParameterWidgetFactory, parent: QWidget) -> None:
        super().__init__(factory, parent)

        assert isinstance(self._body_layout, QGridLayout)

        self.__checkbox = QCheckBox(self._body_widget)
        self.__checkbox.clicked.connect(self.__on_checkbox_click)
        self._body_layout.addWidget(self.__checkbox, 0, 0)
        self._body_layout.setColumnStretch(0, 0)
        self._body_layout.setColumnStretch(1, 1)

    def _create_body_layout(self, note_label_widget: QWidget) -> QLayout:
        """Called by ParameterWidget.__init__"""

        layout = QGridLayout(self._body_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(note_label_widget, 0, 1)
        return layout

    def __on_checkbox_click(self, checked: bool) -> None:
        self.sig_parameter_changed.emit(checked)

    def set_parameter(self, param: Any) -> None:
        with QtCore.QSignalBlocker(self):
            self.__checkbox.setChecked(bool(param))


@attrs.frozen(kw_only=True, slots=False)
class ComboboxParameterWidgetFactory(ParameterWidgetFactory, Generic[T]):
    items: list[tuple[str, T]]

    def create(self, parent: QWidget) -> ComboboxParameterWidget[T]:
        return ComboboxParameterWidget(self, parent)


class ComboboxParameterWidget(ParameterWidget, Generic[T]):
    def __init__(self, factory: ComboboxParameterWidgetFactory[T], parent: QWidget) -> None:
        super().__init__(factory, parent)

        self._combobox = _PidgetComboBox(self._body_widget)
        self._body_layout.addWidget(self._combobox)

        for displayed_text, user_data in factory.items:
            self._combobox.addItem(displayed_text, user_data)

        self._combobox.currentIndexChanged.connect(self.__emit_data_of_combobox_item)

    def __emit_data_of_combobox_item(self, index: int) -> None:
        data = self._combobox.itemData(index)
        self.sig_parameter_changed.emit(data)

    def set_parameter(self, param: Any) -> None:
        with QtCore.QSignalBlocker(self):
            index = self._combobox.findData(param)
            if index == -1:
                raise ValueError(f"Data item {param} could not be found in {self}.")
            self._combobox.setCurrentIndex(index)


@attrs.frozen(kw_only=True, slots=False)
class SensorIdParameterWidgetFactory(ComboboxParameterWidgetFactory[int]):
    name_label_text: str = attrs.field(default="Sensor:")
    name_label_tooltip: str = attrs.field(default="The sensor to use in session")

    def create(self, parent: QWidget) -> SensorIdParameterWidget:
        return SensorIdParameterWidget(self, parent)


class SensorIdParameterWidget(ComboboxParameterWidget[int]):
    _sensor_list: list[int]

    def __init__(self, factory: SensorIdParameterWidgetFactory, parent: QWidget) -> None:
        super().__init__(factory, parent)
        self._sensor_list = []

    def _update_items(self, items: list[tuple[str, int]]) -> None:
        with QtCore.QSignalBlocker(
            self
        ):  # Does not take into account when selected item is removed
            self._combobox.clear()

            for displayed_text, user_data in items:
                self._combobox.addItem(displayed_text, user_data)

    def set_selected_sensor(self, sensor_id: Optional[int], sensor_list: list[int]) -> None:
        if sensor_list != self._sensor_list:
            self._sensor_list = sensor_list
            self._update_items([(str(i), i) for i in sensor_list])

        try:
            super().set_parameter(sensor_id)
        except ValueError:
            self.setEnabled(False)
        else:
            self.setEnabled(True)


@attrs.frozen(kw_only=True, slots=False)
class EnumParameterWidgetFactory(ComboboxParameterWidgetFactory[EnumT]):
    enum_type: Type[EnumT] = attrs.field()
    label_mapping: dict[EnumT, str] = attrs.field()

    items: list[tuple[str, EnumT]] = attrs.field(init=False)

    def __attrs_post_init__(self) -> None:
        if self.label_mapping.keys() != set(self.enum_type):
            raise ValueError("label_mapping does not match enum_type")

        items = [(v, k) for k, v in self.label_mapping.items()]

        # The instance is immutable at this point, which is circumvented by the next row. See:
        # - https://www.attrs.org/en/stable/api.html#attr.ib
        # - https://github.com/python-attrs/attrs/issues/120
        # - https://github.com/python-attrs/attrs/issues/147

        object.__setattr__(self, "items", items)

    def create(self, parent: QWidget) -> EnumParameterWidget[EnumT]:
        return EnumParameterWidget[EnumT](self, parent)


class EnumParameterWidget(ComboboxParameterWidget[EnumT]):
    def __init__(self, factory: EnumParameterWidgetFactory, parent: QWidget) -> None:
        super().__init__(factory, parent)


@attrs.frozen(kw_only=True, slots=False)
class OptionalEnumParameterWidgetFactory(
    OptionalParameterWidgetFactory, EnumParameterWidgetFactory
):
    def create(self, parent: QWidget) -> OptionalEnumParameterWidget:
        return OptionalEnumParameterWidget(self, parent)


class OptionalEnumParameterWidget(OptionalParameterWidget):
    def __init__(self, factory: OptionalEnumParameterWidgetFactory, parent: QWidget) -> None:
        super().__init__(factory, parent)

        self._combobox = _PidgetComboBox(self._body_widget)
        self._body_layout.addWidget(self._combobox)

        for displayed_text, user_data in factory.items:
            self._combobox.addItem(displayed_text, user_data)

        self._none_checkbox.stateChanged.connect(self.__emit_data_of_combobox_or_none)
        self._none_checkbox.stateChanged.connect(self.__enable_combobox_if_checked)
        self._combobox.currentIndexChanged.connect(self.__emit_data_of_combobox_or_none)

    def __emit_data_of_combobox_or_none(self) -> None:
        if self._none_checkbox.isChecked():
            data = self._combobox.currentData()
            self.sig_parameter_changed.emit(data)
        else:
            self.sig_parameter_changed.emit(None)

    def __enable_combobox_if_checked(self) -> None:
        self._combobox.setEnabled(self._none_checkbox.isChecked())

    def set_parameter(self, value: Any) -> None:
        super().set_parameter(value)
        if value is not None:
            self.set_enum_parameter(value)
            self._combobox.setEnabled(True)
        else:
            self._combobox.setEnabled(False)

    def set_enum_parameter(self, param: Any) -> None:
        with QtCore.QSignalBlocker(self):
            index = self._combobox.findData(param)
            if index == -1:
                raise ValueError(f"Data item {param} could not be found in {self}.")
            self._combobox.setCurrentIndex(index)


_WIDGET_WIDTH = 125


class _PidgetComboBox(QComboBox):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)

        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.setFixedWidth(_WIDGET_WIDTH)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class _PidgetSpinBox(QSpinBox):
    def __init__(
        self,
        parent: QWidget,
        *,
        limits: Optional[Tuple[Optional[int], Optional[int]]] = None,
        init_set_value: Optional[int] = None,
        suffix: Optional[str] = None,
    ) -> None:
        super().__init__(parent)

        self.setKeyboardTracking(False)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.setAlignment(QtCore.Qt.AlignRight)
        self.setFixedWidth(_WIDGET_WIDTH)

        self.setRange(*_convert_int_limits_to_qt_range(limits))

        if suffix:
            self.setSuffix(f" {suffix}")

        if init_set_value is not None:
            self.setValue(init_set_value)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class _PidgetDoubleSpinBox(QDoubleSpinBox):
    def __init__(
        self,
        parent: QWidget,
        *,
        limits: Optional[Tuple[Optional[float], Optional[float]]] = None,
        init_set_value: Optional[float] = None,
        decimals: int = 1,
        suffix: Optional[str] = None,
    ) -> None:
        super().__init__(parent)

        self.setKeyboardTracking(False)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.setAlignment(QtCore.Qt.AlignRight)
        self.setFixedWidth(_WIDGET_WIDTH)

        self.setRange(*_convert_float_limits_to_qt_range(limits))
        self.setDecimals(decimals)
        self.setSingleStep(10 ** (-decimals))

        if suffix:
            self.setSuffix(f" {suffix}")

        if init_set_value is not None:
            self.setValue(init_set_value)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class _PidgetFloatSlider(QSlider):
    NUM_STEPS = 1000

    wrapped_value_changed = QtCore.Signal(float)

    def __init__(
        self,
        parent: QWidget,
        *,
        limits: Tuple[float, float],
        decimals: int,
        log_scale: bool,
    ) -> None:
        super().__init__(QtCore.Qt.Horizontal, parent)

        self.limits = limits
        self.decimals = decimals
        self.log_scale = log_scale

        self.setRange(0, self.NUM_STEPS)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)

        self.valueChanged.connect(self.__on_value_changed)

    def __on_value_changed(self, value: int) -> None:
        self.wrapped_value_changed.emit(self.__from_slider_scale(value))

    def wrapped_set_value(self, value: float) -> None:
        self.setValue(self.__to_slider_scale(value))

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()

    def __to_slider_scale(self, x: float) -> int:
        lower, upper = self.limits

        if self.log_scale:
            lower = np.log(lower)
            upper = np.log(upper)
            x = np.log(x)

        y = (x - lower) / (upper - lower) * self.NUM_STEPS
        return int(round(y))

    def __from_slider_scale(self, y: int) -> float:
        lower, upper = self.limits

        if self.log_scale:
            lower = np.log(lower)
            upper = np.log(upper)

        x = y / self.NUM_STEPS * (upper - lower) + lower

        if self.log_scale:
            x = np.exp(x)

        return round(x, self.decimals)


def _convert_int_limits_to_qt_range(
    limits: Optional[Tuple[Optional[int], Optional[int]]]
) -> Tuple[int, int]:
    if limits is None:
        limits = (None, None)

    lower, upper = limits

    if lower is None:
        lower = int(-1e9)

    if upper is None:
        upper = int(1e9)

    return (lower, upper)


def _convert_float_limits_to_qt_range(
    limits: Optional[Tuple[Optional[float], Optional[float]]]
) -> Tuple[float, float]:
    if limits is None:
        limits = (None, None)

    lower, upper = limits

    if lower is None:
        lower = -1e9

    if upper is None:
        upper = 1e9

    return (lower, upper)
