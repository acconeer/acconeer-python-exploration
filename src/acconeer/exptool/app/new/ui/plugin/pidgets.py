from __future__ import annotations

from abc import abstractmethod
from enum import Enum
from typing import Any, Generic, Optional, Type, TypeVar

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
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


class ParameterWidget(QWidget):
    """Base class for a parameter-bound widget.

    A ``ParameterWidget`` comes with a
    ``name`` label and an ``note`` label by default.

        +------------------+------------------+
        |              name label             |
        +------------------+------------------+
        |           parameter widget          |
        +------------------+------------------+
        |    note label (sometimes hidden)    |
        +-------------------------------------+
    :param parameter_widget:
        The widget that lets the user edit the parameter.
    :param name_label_text: The text to display in the ``label`` segment
    :param note_label_text: The text to display in the ``note`` segment
    """

    sig_parameter_changed = Signal(object)

    def __init__(
        self,
        parameter_widget: QWidget,
        name_label_text: str,
        note_label_text: str = "",
        name_parameter_layout: Type[QLayout] = QVBoxLayout,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent=parent)
        vert_layout = name_parameter_layout(parent=self)

        self.parameter_widget = parameter_widget
        self.note_label_widget = QLabel(parent=self)
        self.label_widget = QLabel(name_label_text, parent=self)
        self.note_label_widget.setWordWrap(True)
        self.note_label_widget.setContentsMargins(5, 5, 5, 5)
        self.set_note_text(note_label_text)

        vert_layout.addWidget(self.label_widget)
        vert_layout.addWidget(self.parameter_widget)
        vert_layout.addWidget(self.note_label_widget)
        self.setLayout(vert_layout)

    def set_note_text(self, message: str, criticality: Optional[Criticality] = None) -> None:
        if message == "":
            self.note_label_widget.hide()
            return

        COLOR_MAP = {
            Criticality.ERROR: "#E6635A",
            Criticality.WARNING: "#FCC842",
            None: "white",
        }

        self.note_label_widget.show()
        self.note_label_widget.setText(message)
        self.note_label_widget.setStyleSheet(
            f"background-color: {COLOR_MAP[criticality]}; color: white; font: bold italic;"
        )

    @abstractmethod
    def set_parameter(self, value: Any) -> None:
        pass


class OptionalParameterWidget(ParameterWidget):
    """Optional parameter, not optional widget"""

    def __init__(
        self,
        optional_parameter_widget: QWidget,
        name_label_text: str,
        note_label_text: str = "",
        parent: Optional[QWidget] = None,
    ):
        layout = QHBoxLayout(parent=self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.none_checkbox = QCheckBox()
        self.optional_parameter_widget = optional_parameter_widget

        layout.addWidget(self.none_checkbox)
        layout.addWidget(self.optional_parameter_widget)

        super().__init__(
            parameter_widget=widget_wrap_layout(layout),
            name_label_text=name_label_text,
            note_label_text=note_label_text,
            parent=parent,
        )

    def set_parameter(self, value: Any) -> None:
        if value is None:
            self.none_checkbox.setChecked(False)
            self.optional_parameter_widget.setEnabled(False)
        else:
            self.none_checkbox.setChecked(True)
            self.optional_parameter_widget.setEnabled(True)
            self.set_not_none_parameter(value)

    @abstractmethod
    def set_not_none_parameter(self, value: Any) -> None:
        pass


class OptionalTextParameterWidget(OptionalParameterWidget):
    def __init__(
        self,
        name_label_text: str,
        note_label_text: str = "",
        parent: Optional[QWidget] = None,
    ):
        self.line_edit = QLineEdit()
        super().__init__(
            optional_parameter_widget=self.line_edit,
            name_label_text=name_label_text,
            note_label_text=note_label_text,
            parent=parent,
        )
        self.none_checkbox.stateChanged.connect(self.emit_none_if_checkbox_is_unchecked)
        self.none_checkbox.stateChanged.connect(self.emit_line_edit_text_if_checkbox_is_checked)
        self.none_checkbox.stateChanged.connect(self.line_edit_enable_based_on_checkbox_state)
        self.line_edit.editingFinished.connect(self.emit_line_edit_text_if_non_empty)

    def emit_none_if_checkbox_is_unchecked(self, checked_state: int) -> None:
        if checked_state == 0:  # 0 <=> unchecked
            self.sig_parameter_changed.emit(None)

    def emit_line_edit_text_if_non_empty(self) -> None:
        if self.line_edit.text() != "":
            self.sig_parameter_changed.emit(self.line_edit.text())

    def emit_line_edit_text_if_checkbox_is_checked(self, checked_state: int) -> None:
        if checked_state == 2:  # 2 <=> checked
            self.emit_line_edit_text_if_non_empty()

    def line_edit_enable_based_on_checkbox_state(self, checked_state: int) -> None:
        self.line_edit.setEnabled(checked_state == 2)  # 2 <=> checked

    def set_not_none_parameter(self, value: Any) -> None:
        self.line_edit.setText(str(value))


class TextParameterWidget(ParameterWidget):
    def __init__(
        self, name_label_text: str, note_label_text: str = "", parent: Optional[QWidget] = None
    ) -> None:
        self.line_edit = QLineEdit()
        super().__init__(
            parameter_widget=self.line_edit,
            name_label_text=name_label_text,
            note_label_text=note_label_text,
            parent=parent,
        )
        self.line_edit.textChanged.connect(self.emit_change_if_string_is_not_empty)

    def set_parameter(self, new_text: Any) -> None:
        self.line_edit.setText(str(new_text))

    def emit_change_if_string_is_not_empty(self, string: str) -> None:
        if string != "":
            self.sig_parameter_changed.emit(string)


class CheckboxParameterWidget(ParameterWidget):
    def __init__(
        self, name_label_text: str, note_label_text: str = "", parent: Optional[QWidget] = None
    ) -> None:
        self.checkbox = QCheckBox()
        super().__init__(
            parameter_widget=self.checkbox,
            name_label_text=name_label_text,
            note_label_text=note_label_text,
            name_parameter_layout=QHBoxLayout,
            parent=parent,
        )
        self.checkbox.clicked.connect(self._on_checkbox_click)

    def _on_checkbox_click(self, checked: bool) -> None:
        self.sig_parameter_changed.emit(checked)

    def set_parameter(self, param: Any) -> None:
        self.checkbox.setChecked(bool(param))


class ComboboxParameterWidget(ParameterWidget, Generic[T]):
    def __init__(
        self,
        items: list[tuple[str, T]],
        name_label_text: str,
        note_label_text: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        self.combobox = QComboBox()
        super().__init__(
            parameter_widget=self.combobox,
            name_label_text=name_label_text,
            note_label_text=note_label_text,
            parent=parent,
        )
        for displayed_text, user_data in items:
            self.combobox.addItem(displayed_text, user_data)
        self.combobox.currentIndexChanged.connect(self.emit_data_of_combobox_item)

    def emit_data_of_combobox_item(self, index: int) -> None:
        data = self.combobox.itemData(index)
        self.sig_parameter_changed.emit(data)

    def set_parameter(self, param: Any) -> None:
        index = self.combobox.findData(param)
        if index == -1:
            raise ValueError(f"Data item {param} could not be found in {self}.")
        self.combobox.setCurrentIndex(index)


class EnumParameterWidget(ComboboxParameterWidget[EnumT]):
    def __init__(
        self,
        enum_type: Type[EnumT],
        name_label_text: str,
        note_label_text: str = "",
        label_mapping: dict[EnumT, str] = {},
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(
            items=[(label_mapping.get(member, member.name), member) for member in enum_type],
            name_label_text=name_label_text,
            note_label_text=note_label_text,
            parent=parent,
        )
