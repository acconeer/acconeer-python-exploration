# Copyright (c) Acconeer AB, 2022-2025
# All rights reserved

from __future__ import annotations

import abc
from enum import Enum
from typing import (
    Any,
    Callable,
    Collection,
    Generic,
    Iterable,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
)

import attrs
import numpy as np
import typing_extensions as te

from PySide6 import QtCore, QtGui
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QWidget,
)

from acconeer.exptool._core.entities.validation_result import Criticality
from acconeer.exptool.app.new.ui import icons
from acconeer.exptool.app.new.ui.components.data_editor import DataEditor

from .common import MaybeIterable, as_sequence


def widget_wrap_layout(layout: QLayout) -> QWidget:
    dummy = QWidget()
    dummy.setLayout(layout)
    return dummy


PidgetHook = Callable[["Pidget", Mapping[str, "Pidget"]], None]
T = TypeVar("T")
EnumT = TypeVar("EnumT", bound=Enum)


def _hooks_converter(a: MaybeIterable[PidgetHook]) -> Sequence[PidgetHook]:
    return as_sequence(a)


@attrs.frozen(kw_only=True, slots=False)
class PidgetFactory(abc.ABC):
    name_label_text: str = attrs.field()
    name_label_tooltip: Optional[str] = None
    note_label_text: Optional[str] = None
    extra_widget_factory: Callable[[], Optional[QWidget]] = lambda: None
    hooks: Sequence[PidgetHook] = attrs.field(factory=tuple, converter=_hooks_converter)

    @name_label_text.validator
    def check_for_whitespaces(self, attribute: Any, value: str) -> None:
        if value != value.strip():
            msg = "Labels cannot start or end with a whitespace"
            raise ValueError(msg)

    @name_label_text.validator
    def check_label_text_format(self, attribute: Any, value: str) -> None:
        if len(value) > 0 and value[-1] != ":":
            msg = "Labels have to end with ':'"
            raise ValueError(msg)

    @abc.abstractmethod
    def create(self, parent: QWidget) -> Pidget: ...

    def create_name_label(self, parent: QWidget) -> QLabel:
        label = QLabel(self.name_label_text, parent=parent)
        if self.name_label_tooltip is not None:
            label.setToolTip(self.name_label_tooltip)
        return label

    def create_note_label(self, parent: QWidget) -> QLabel:
        label = QLabel(parent=parent)
        label.setWordWrap(True)
        label.setContentsMargins(5, 5, 5, 5)
        return label


class Pidget(DataEditor[Any]):
    """Base class for a parameter-bound widget.

    A ``Pidget`` comes with a
    ``name`` label and an ``note`` label by default.
    """

    sig_update = QtCore.Signal(object)

    def __init__(self, factory: PidgetFactory, parent: QWidget) -> None:
        super().__init__(parent=parent)
        self.__note_widget = factory.create_note_label(self)

    def set_standard_layout(
        self,
        factory: PidgetFactory,
        *,
        first_row_elements: Iterable[
            Union[
                QWidget,
                te.Literal["name_label", "extra_widget"],
            ]
        ],
        full_row_widgets: Collection[QWidget] = (),
        colstretch: tuple[int, ...] = (),
    ) -> None:
        """
        Arranges the element according to a "standard layout"

        +---------------+-----+-----+-----+
        |               |     |     |     |
        |  first_row[0] | fr1 | fr2 | ... |
        |               |     |     |     |
        |---------------+-----+-----+-----+
        |                                 |
        |            Note label           |
        |                                 |
        +---------------------------------+

        And if ``full_row_widgets`` is specified:

        +---------------+-----+-----+-----+
        |               |     |     |     |
        |  first_row[0] | fr1 | fr2 | ... |
        |               |     |     |     |
        +---------------+-----+-----+-----+
        |         Full row widget[0]      |
        +---------------------------------+
        |         Full row widget[1]      |
        +---------------------------------+
        |                ...              |
        +---------------------------------+
        |                                 |
        |            Note label           |
        |                                 |
        +---------------------------------+

        Special strings can be elements in the ``first_row_widgets``. The strings are
        replaced with a widget internally.
        """
        layout = QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.set_note_text(factory.note_label_text)

        num_name_labels = sum(e == "name_label" for e in first_row_elements)
        if num_name_labels > 1:
            msg = "At most 1 'name_label' should be specified."
            raise ValueError(msg)

        num_extra_widget = sum(e == "extra_widget" for e in first_row_elements)
        if num_extra_widget > 1:
            msg = "At most 1 'extra_widget' should be specified."
            raise ValueError(msg)

        for col, elem in enumerate(first_row_elements):
            if elem == "name_label":
                name_label = factory.create_name_label(self)
                layout.addWidget(name_label, 0, col)
            elif elem == "extra_widget":
                if (extra_widget := factory.extra_widget_factory()) is not None:
                    layout.addWidget(extra_widget, 0, col, QtCore.Qt.AlignmentFlag.AlignLeft)
            else:
                layout.addWidget(elem, 0, col)

        for column, stretch in enumerate(colstretch):
            layout.setColumnStretch(column, stretch)

        for row, row_widget in enumerate(full_row_widgets, start=1):
            layout.addWidget(row_widget, row, 0, 1, -1)

        layout.addWidget(self.__note_widget, 1 + len(full_row_widgets), 0, 1, -1)

        self.setLayout(layout)

    def set_note_text(
        self, message: Optional[str], criticality: Optional[Criticality] = None
    ) -> None:
        if not message:
            self.__note_widget.hide()
            return

        COLOR_MAP = {
            Criticality.ERROR: icons.ERROR_RED,
            Criticality.WARNING: icons.WARNING_YELLOW,
            None: "white",
        }

        self.__note_widget.show()
        self.__note_widget.setText(message)
        self.__note_widget.setStyleSheet(
            f"background-color: {COLOR_MAP[criticality]}; color: white; font: bold italic;"
        )

    def setEnabled(self, enabled: bool) -> None:
        super(DataEditor, self).setEnabled(enabled)

    @abc.abstractmethod
    def set_data(self, value: Any) -> None:
        pass

    @abc.abstractmethod
    def get_data(self) -> Any:
        pass

    @property
    def is_ready(self) -> bool:
        return not self.__note_widget.isVisible()


@attrs.frozen(kw_only=True, slots=False)
class IntPidgetFactory(PidgetFactory):
    limits: Optional[Tuple[Optional[int], Optional[int]]] = None
    suffix: Optional[str] = None

    def create(self, parent: QWidget) -> IntPidget:
        return IntPidget(self, parent)


class IntPidget(Pidget):
    def __init__(self, factory: IntPidgetFactory, parent: QWidget) -> None:
        super().__init__(factory, parent)

        self._spin_box = _PidgetSpinBox(
            self,
            limits=factory.limits,
            suffix=factory.suffix,
        )
        self._spin_box.valueChanged.connect(self.__on_changed)

        self.set_standard_layout(
            factory,
            first_row_elements=["name_label", "extra_widget", self._spin_box],
        )

    def set_data(self, value: Any) -> None:
        assert isinstance(value, int)

        with QtCore.QSignalBlocker(self):
            self._spin_box.setValue(value)

    def get_data(self) -> int:
        return int(self._spin_box.value())

    def __on_changed(self) -> None:
        self.sig_update.emit(self._spin_box.value())


@attrs.frozen(kw_only=True, slots=False)
class StrPidgetFactory(PidgetFactory):
    def create(self, parent: QWidget) -> StrPidget:
        return StrPidget(self, parent)


class StrPidget(Pidget):
    def __init__(self, factory: StrPidgetFactory, parent: QWidget) -> None:
        super().__init__(factory, parent)

        self._line_edit = QLineEdit(self)
        self._line_edit.setMaximumWidth(WIDGET_WIDTH)
        self._line_edit.editingFinished.connect(self.__on_changed)

        self.set_standard_layout(
            factory,
            first_row_elements=["name_label", "extra_widget", self._line_edit],
        )

    def set_data(self, value: Any) -> None:
        assert isinstance(value, str)

        with QtCore.QSignalBlocker(self):
            self._line_edit.setText(value)

    def get_data(self) -> str:
        return str(self._line_edit.text())

    def __on_changed(self) -> None:
        self.sig_update.emit(self.get_data())


@attrs.frozen(kw_only=True, slots=False)
class FloatPidgetFactory(PidgetFactory):
    limits: Optional[Tuple[Optional[float], Optional[float]]] = None
    suffix: Optional[str] = None
    decimals: int = 1

    def create(self, parent: QWidget) -> FloatPidget:
        return FloatPidget(self, parent)


class FloatPidget(Pidget):
    def __init__(self, factory: FloatPidgetFactory, parent: QWidget) -> None:
        super().__init__(factory, parent)

        self._spin_box = _PidgetDoubleSpinBox(
            self,
            limits=factory.limits,
            suffix=factory.suffix,
            decimals=factory.decimals,
        )
        self._spin_box.valueChanged.connect(self.__on_changed)

        self.set_standard_layout(
            factory,
            first_row_elements=["name_label", "extra_widget", self._spin_box],
        )

    def set_data(self, value: Any) -> None:
        assert isinstance(value, (int, float))

        with QtCore.QSignalBlocker(self):
            self._spin_box.setValue(value)

    def get_data(self) -> float:
        return float(self._spin_box.value())

    def __on_changed(self) -> None:
        self.sig_update.emit(self._spin_box.value())


@attrs.frozen(kw_only=True, slots=False)
class FloatSliderPidgetFactory(FloatPidgetFactory):
    limits: Tuple[float, float]
    log_scale: bool = False
    show_limit_values: bool = True
    limit_texts: Optional[Tuple[Optional[str], Optional[str]]] = None

    def __attrs_post_init__(self) -> None:
        if self.log_scale and self.limits[0] <= 0:
            msg = "Lower limit must be > 0 when using log scale"
            raise ValueError(msg)

    def create(self, parent: QWidget) -> FloatSliderPidget:  # type: ignore[override]
        return FloatSliderPidget(self, parent)


class FloatSliderPidget(Pidget):
    def __init__(self, factory: FloatSliderPidgetFactory, parent: QWidget) -> None:
        super().__init__(factory, parent)

        self.__spin_box = _PidgetDoubleSpinBox(
            self,
            limits=factory.limits,
            suffix=factory.suffix,
            decimals=factory.decimals,
        )
        self.__spin_box.valueChanged.connect(self.__on_spin_box_changed)

        slider_widget = QWidget(self)
        slider_widget_layout = QHBoxLayout(slider_widget)
        slider_widget_layout.setContentsMargins(11, 6, 11, 0)

        lower_limit, upper_limit = factory.limits
        if factory.show_limit_values:
            slider_widget_layout.addWidget(QLabel(str(lower_limit), slider_widget))

        self._slider = _PidgetFloatSlider(
            slider_widget,
            limits=factory.limits,
            decimals=factory.decimals,
            log_scale=factory.log_scale,
        )
        self._slider.wrapped_value_changed.connect(self.__on_slider_changed)
        slider_widget_layout.addWidget(self._slider)

        if factory.show_limit_values:
            slider_widget_layout.addWidget(QLabel(str(upper_limit), slider_widget))

        if factory.limit_texts is not None:
            label_text_widget = QWidget(self)
            label_text_widget_layout = QHBoxLayout(label_text_widget)
            label_text_widget.setLayout(label_text_widget_layout)

            label_text_widget_layout.setContentsMargins(11, 0, 11, 0)
            label_text_widget_layout.setSpacing(0)

            left, right = factory.limit_texts

            if left is not None:
                label = QLabel(left, label_text_widget)
                label_text_widget_layout.addWidget(label)

            label_text_widget_layout.addStretch(1)

            if right is not None:
                label = QLabel(right, label_text_widget)
                label_text_widget_layout.addWidget(label)

            full_row_widgets = [slider_widget, label_text_widget]
        else:
            full_row_widgets = [slider_widget]

        slider_widget.setLayout(slider_widget_layout)

        self.set_standard_layout(
            factory,
            first_row_elements=["name_label", "extra_widget", self.__spin_box],
            full_row_widgets=full_row_widgets,
        )

    def set_data(self, value: Any) -> None:
        assert isinstance(value, (int, float))

        with QtCore.QSignalBlocker(self):
            self.__spin_box.setValue(value)
            self._slider.wrapped_set_value(value)

    def get_data(self) -> float:
        return float(self.__spin_box.value())

    def __on_spin_box_changed(self, value: float) -> None:
        with QtCore.QSignalBlocker(self):
            self._slider.wrapped_set_value(value)

        self.sig_update.emit(value)

    def __on_slider_changed(self, value: float) -> None:
        with QtCore.QSignalBlocker(self):
            self.__spin_box.setValue(value)

        self.sig_update.emit(value)


@attrs.frozen(kw_only=True, slots=False)
class OptionalPidgetFactory(PidgetFactory):
    checkbox_label_text: Optional[str] = None


class OptionalPidget(Pidget):
    """Optional parameter, not optional widget"""

    def __init__(self, factory: OptionalPidgetFactory, parent: QWidget) -> None:
        super().__init__(factory, parent)

        self._none_checkbox = QCheckBox(self)
        if factory.checkbox_label_text:
            self._none_checkbox.setText(factory.checkbox_label_text)

    def set_standard_layout(
        self,
        factory: PidgetFactory,
        *,
        first_row_elements: Iterable[
            Union[
                QWidget,
                te.Literal["name_label", "extra_widget", "optional_checkbox"],
            ]
        ],
        full_row_widgets: Collection[QWidget] = (),
        colstretch: tuple[int, ...] = (),
    ) -> None:
        num_optional_checkboxes = sum(e == "optional_checkbox" for e in first_row_elements)
        if num_optional_checkboxes != 1:
            msg = "Exactly 1 'optional_checkbox' should be specified."
            raise ValueError(msg)

        super().set_standard_layout(
            factory,
            first_row_elements=[
                (self._none_checkbox if e == "optional_checkbox" else e)
                for e in first_row_elements
            ],
            full_row_widgets=full_row_widgets,
            colstretch=colstretch,
        )

    def set_data(self, value: Any) -> None:
        with QtCore.QSignalBlocker(self):
            self._none_checkbox.setChecked(value is not None)

    @abc.abstractmethod
    def get_data(self) -> Optional[Any]:
        pass


@attrs.frozen(kw_only=True, slots=False)
class OptionalIntPidgetFactory(OptionalPidgetFactory, IntPidgetFactory):
    init_set_value: Optional[int] = None

    def create(self, parent: QWidget) -> OptionalIntPidget:  # type: ignore[override]
        return OptionalIntPidget(self, parent)


class OptionalIntPidget(OptionalPidget):
    def __init__(self, factory: OptionalIntPidgetFactory, parent: QWidget) -> None:
        super().__init__(factory, parent)

        self._none_checkbox.stateChanged.connect(self.__on_changed)

        self._spin_box = _PidgetSpinBox(
            self,
            limits=factory.limits,
            suffix=factory.suffix,
            init_set_value=factory.init_set_value,
        )
        self._spin_box.valueChanged.connect(self.__on_changed)

        self.set_standard_layout(
            factory,
            first_row_elements=["name_label", "extra_widget", "optional_checkbox", self._spin_box],
            colstretch=(1,),
        )

    def __on_changed(self) -> None:
        checked = self._none_checkbox.isChecked()

        with QtCore.QSignalBlocker(self):
            self._spin_box.setEnabled(checked)

        value = self._spin_box.value() if checked else None
        self.sig_update.emit(value)

    def set_data(self, value: Any) -> None:
        super().set_data(value)

        with QtCore.QSignalBlocker(self):
            if value is None:
                self._spin_box.setEnabled(False)
            else:
                self._spin_box.setValue(value)
                self._spin_box.setEnabled(True)

    def get_data(self) -> Optional[int]:
        if not self._none_checkbox.isChecked():
            return None
        else:
            return int(self._spin_box.value())


@attrs.frozen(kw_only=True, slots=False)
class OptionalFloatPidgetFactory(OptionalPidgetFactory, FloatPidgetFactory):
    init_set_value: Optional[float] = None
    """
    The initial value of the spinbox (ignoring the None-ness of the pidget)
    """

    placeholder_text: Optional[str] = None
    """
    Text that will be displayed when the checkbox is unchecked (and data is None).
    placeholder_text = None disables the placeholder text entierly
    """

    def create(self, parent: QWidget) -> OptionalFloatPidget:  # type: ignore[override]
        return OptionalFloatPidget(self, parent)


class OptionalFloatPidget(OptionalPidget):
    _SPINBOX_INDEX = 0
    _DUMMY_INDEX = 1

    def __init__(self, factory: OptionalFloatPidgetFactory, parent: QWidget) -> None:
        super().__init__(factory, parent)

        self._none_checkbox.stateChanged.connect(self.__on_changed)

        self._container = QStackedWidget()
        self._container.setContentsMargins(0, 0, 0, 0)
        self._spin_box = _PidgetDoubleSpinBox(
            self._container,
            decimals=factory.decimals,
            limits=factory.limits,
            suffix=factory.suffix,
            init_set_value=factory.init_set_value,
        )
        self._spin_box.valueChanged.connect(self.__on_changed)
        self._container.addWidget(self._spin_box)

        if factory.placeholder_text is None:
            self._dummy_spin_box = None
        else:
            self._dummy_spin_box = _PidgetDoubleSpinBox.placeholder_dummy(
                self._container, factory.placeholder_text
            )
            self._dummy_spin_box.setEnabled(False)
            self._container.addWidget(self._dummy_spin_box)

        self.set_standard_layout(
            factory,
            first_row_elements=[
                "name_label",
                "extra_widget",
                "optional_checkbox",
                self._container,
            ],
            colstretch=(1,),
        )

    def __on_changed(self) -> None:
        checked = self._none_checkbox.isChecked()

        with QtCore.QSignalBlocker(self):
            if self._dummy_spin_box is None:
                self._spin_box.setEnabled(checked)
            else:
                self._container.setCurrentIndex(
                    self._SPINBOX_INDEX if checked else self._DUMMY_INDEX
                )

        value = self._spin_box.value() if checked else None
        self.sig_update.emit(value)

    def set_data(self, value: Any) -> None:
        super().set_data(value)

        if value is not None:
            with QtCore.QSignalBlocker(self):
                self._spin_box.setValue(value)

        if self._dummy_spin_box is None:
            self._spin_box.setEnabled(value is not None)
        else:
            self._container.setCurrentIndex(
                self._SPINBOX_INDEX if value is not None else self._DUMMY_INDEX
            )

    def get_data(self) -> Optional[float]:
        if not self._none_checkbox.isChecked():
            return None
        else:
            return float(self._spin_box.value())


@attrs.frozen(kw_only=True, slots=False)
class CheckboxPidgetFactory(PidgetFactory):
    name_label_text: str = attrs.field()

    def create(self, parent: QWidget) -> CheckboxPidget:
        return CheckboxPidget(self, parent)

    @name_label_text.validator
    def check_for_whitespaces(self, attribute: Any, value: str) -> None:
        if value != value.strip():
            msg = "Labels cannot start or end with a whitespace"
            raise ValueError(msg)

    @name_label_text.validator
    def check_label_text_format(self, attribute: Any, value: str) -> None:
        if len(value) > 0 and value[-1] == ":":
            msg = "Checkbox labels cannot end with ':'"
            raise ValueError(msg)


class CheckboxPidget(Pidget):
    def __init__(self, factory: CheckboxPidgetFactory, parent: QWidget) -> None:
        super().__init__(factory, parent)

        self._checkbox = QCheckBox(self)
        self._checkbox.setText(factory.name_label_text)
        self._checkbox.clicked.connect(self.__on_checkbox_click)

        self.set_standard_layout(
            factory,
            first_row_elements=[self._checkbox, "extra_widget"],
            colstretch=(0, 1),
        )

    def __on_checkbox_click(self, checked: bool) -> None:
        self.sig_update.emit(checked)

    def set_data(self, param: Any) -> None:
        with QtCore.QSignalBlocker(self):
            self._checkbox.setChecked(bool(param))

    def get_data(self) -> bool:
        return bool(self._checkbox.isChecked())


@attrs.frozen(kw_only=True, slots=False)
class ComboboxPidgetFactory(PidgetFactory, Generic[T]):
    items: list[tuple[str, T]]

    def create(self, parent: QWidget) -> ComboboxPidget[T]:
        return ComboboxPidget(self, parent)


class ComboboxPidget(Pidget, Generic[T]):
    def __init__(self, factory: ComboboxPidgetFactory[T], parent: QWidget) -> None:
        super().__init__(factory, parent)

        self._combobox = PidgetComboBox(self)

        for displayed_text, user_data in factory.items:
            self._combobox.addItem(displayed_text, user_data)

        self._combobox.currentIndexChanged.connect(self._emit_data_of_combobox_item)

        self.set_standard_layout(
            factory,
            first_row_elements=["name_label", "extra_widget", self._combobox],
        )

    def _emit_data_of_combobox_item(self, index: int) -> None:
        data = self._combobox.itemData(index)
        self.sig_update.emit(data)

    def set_data(self, param: Any) -> None:
        with QtCore.QSignalBlocker(self):
            index = self._combobox.findData(param)
            if index == -1:
                msg = f"Data item {param} could not be found in {self}."
                raise ValueError(msg)
            self._combobox.setCurrentIndex(index)

    def get_data(self) -> T:
        return cast(T, self._combobox.currentData())


@attrs.frozen(kw_only=True, slots=False)
class SensorIdPidgetFactory(ComboboxPidgetFactory[int]):
    name_label_text: str = attrs.field(default="Sensor:")
    name_label_tooltip: str = attrs.field(default="The sensor to use in session")

    def create(self, parent: QWidget) -> SensorIdPidget:
        return SensorIdPidget(self, parent)


class SensorIdPidget(ComboboxPidget[int]):
    def __init__(self, factory: SensorIdPidgetFactory, parent: QWidget) -> None:
        super().__init__(factory, parent)
        self._sensor_id = 1
        self.set_data(self._sensor_id)

    def _emit_data_of_combobox_item(self, index: int) -> None:
        data = self._combobox.itemData(index)

        if data is None:
            return

        self._sensor_id = data
        self.sig_update.emit(data)

    def set_selectable_sensors(self, sensor_list: list[int]) -> None:
        with QtCore.QSignalBlocker(self):
            self._combobox.clear()

            for sensor_id in sensor_list:
                self._combobox.addItem(str(sensor_id), sensor_id)

            self.set_data(self._sensor_id)

    def set_data(self, sensor_id: int) -> None:
        self._sensor_id = sensor_id

        try:
            super().set_data(sensor_id)
        except ValueError:
            with QtCore.QSignalBlocker(self):
                self._combobox.setCurrentIndex(-1)

            self._combobox.setPlaceholderText(f"{self._sensor_id} (unavailable)")

    def get_data(self) -> int:
        return self._sensor_id


@attrs.frozen(kw_only=True, slots=False)
class EnumPidgetFactory(ComboboxPidgetFactory[EnumT]):
    enum_type: Type[EnumT] = attrs.field()
    label_mapping: dict[EnumT, str] = attrs.field()

    items: list[tuple[str, EnumT]] = attrs.field(init=False)

    def __attrs_post_init__(self) -> None:
        if self.label_mapping.keys() != set(self.enum_type):
            msg = "label_mapping does not match enum_type"
            raise ValueError(msg)

        items = [(v, k) for k, v in self.label_mapping.items()]

        # The instance is immutable at this point, which is circumvented by the next row. See:
        # - https://www.attrs.org/en/stable/api.html#attr.ib
        # - https://github.com/python-attrs/attrs/issues/120
        # - https://github.com/python-attrs/attrs/issues/147

        object.__setattr__(self, "items", items)

    def create(self, parent: QWidget) -> EnumPidget[EnumT]:
        return EnumPidget[EnumT](self, parent)


class EnumPidget(ComboboxPidget[EnumT]):
    def __init__(self, factory: EnumPidgetFactory[EnumT], parent: QWidget) -> None:
        super().__init__(factory, parent)


@attrs.frozen(kw_only=True, slots=False)
class OptionalEnumPidgetFactory(OptionalPidgetFactory, EnumPidgetFactory[EnumT]):
    def create(self, parent: QWidget) -> OptionalEnumPidget:  # type: ignore[override]
        return OptionalEnumPidget(self, parent)


class OptionalEnumPidget(OptionalPidget):
    def __init__(self, factory: OptionalEnumPidgetFactory[EnumT], parent: QWidget) -> None:
        super().__init__(factory, parent)

        self._combobox = PidgetComboBox(self)

        for displayed_text, user_data in factory.items:
            self._combobox.addItem(displayed_text, user_data)

        self._none_checkbox.stateChanged.connect(self.__emit_data_of_combobox_or_none)
        self._none_checkbox.stateChanged.connect(self.__enable_combobox_if_checked)
        self._combobox.currentIndexChanged.connect(self.__emit_data_of_combobox_or_none)

        self.set_standard_layout(
            factory,
            first_row_elements=["name_label", "extra_widget", "optional_checkbox", self._combobox],
            colstretch=(1,),
        )

    def __emit_data_of_combobox_or_none(self) -> None:
        if self._none_checkbox.isChecked():
            data = self._combobox.currentData()
            self.sig_update.emit(data)
        else:
            self.sig_update.emit(None)

    def __enable_combobox_if_checked(self) -> None:
        self._combobox.setEnabled(self._none_checkbox.isChecked())

    def set_data(self, value: Any) -> None:
        super().set_data(value)
        if value is not None:
            self.set_enum_parameter(value)
            self._combobox.setEnabled(True)
        else:
            self._combobox.setEnabled(False)

    def get_data(self) -> Optional[Enum]:
        if not self._none_checkbox.isChecked():
            return None
        else:
            return cast(Enum, self._combobox.currentData())

    def set_enum_parameter(self, param: Any) -> None:
        with QtCore.QSignalBlocker(self):
            index = self._combobox.findData(param)
            if index == -1:
                msg = f"Data item {param} could not be found in {self}."
                raise ValueError(msg)
            self._combobox.setCurrentIndex(index)


WIDGET_WIDTH = 125


class PidgetComboBox(QComboBox):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)

        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.setFixedWidth(WIDGET_WIDTH)

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
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        self.setFixedWidth(WIDGET_WIDTH)

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
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        self.setFixedWidth(WIDGET_WIDTH)

        self.setRange(*_convert_float_limits_to_qt_range(limits))
        self.setDecimals(decimals)
        self.setSingleStep(10 ** (-decimals))

        if suffix:
            self.setSuffix(f" {suffix}")

        if init_set_value is not None:
            self.setValue(init_set_value)

    @classmethod
    def placeholder_dummy(cls, parent: QWidget, placeholder_text: str) -> _PidgetDoubleSpinBox:
        """
        Create a spinbox that only displays a placeholder text
        """
        spin_box = _PidgetDoubleSpinBox(parent)
        spin_box.setSpecialValueText(placeholder_text)
        spin_box.setRange(0, 1)
        spin_box.setValue(0)
        spin_box.setReadOnly(True)
        return spin_box

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
        super().__init__(QtCore.Qt.Orientation.Horizontal, parent)

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
    limits: Optional[Tuple[Optional[int], Optional[int]]],
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
    limits: Optional[Tuple[Optional[float], Optional[float]]],
) -> Tuple[float, float]:
    if limits is None:
        limits = (None, None)

    lower, upper = limits

    if lower is None:
        lower = -1e9

    if upper is None:
        upper = 1e9

    return (lower, upper)
