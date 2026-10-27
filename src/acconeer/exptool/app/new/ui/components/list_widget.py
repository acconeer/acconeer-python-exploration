# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import typing as t

from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from acconeer.exptool._core.entities.validation_result import ValidationResult
from acconeer.exptool.app.new.ui import icons

from .attrs_config_editor import AttrsConfigEditor
from .data_editor import DataEditor
from .group_box import GroupBox
from .json_save_load_buttons import JsonPresentable
from .types import PidgetFactoryMapping, PidgetGroupFactoryMapping


ItemT = t.TypeVar("ItemT", bound=JsonPresentable)


class ListWidget(DataEditor[t.List[ItemT]], t.Generic[ItemT]):
    """A variable-length list of ``AttrsConfigEditor`` rows, boxed like one.

    Unlike a ``Pidget``, this is never a field inside another
    ``AttrsConfigEditor`` -- it stands on its own, alongside other
    ``AttrsConfigEditor``s, built out of one of them per row.
    ``item_type``/``item_factory_mapping`` configure that per-row editor
    exactly like any other ``AttrsConfigEditor`` use.
    """

    def __init__(
        self,
        *,
        title: str,
        item_type: t.Type[ItemT],
        item_factory_mapping: t.Union[PidgetFactoryMapping, PidgetGroupFactoryMapping],
        make_default_item: t.Callable[[], ItemT],
        item_title: str = "",
        add_button_text: str = "Add",
        tooltip: t.Optional[str] = None,
        parent: t.Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent=parent)
        self._item_type = item_type
        self._item_factory_mapping = item_factory_mapping
        self._make_default_item = make_default_item
        self._item_title = item_title

        self._rows: list[tuple[AttrsConfigEditor[ItemT], QPushButton, QWidget]] = []

        self._rows_layout = QVBoxLayout()
        self._rows_layout.setContentsMargins(0, 0, 0, 0)

        self._add_button = QPushButton(icons.PLUS(), add_button_text)
        self._add_button.setFlat(True)
        self._add_button.clicked.connect(self._on_add_clicked)

        group_box = GroupBox.vertical(title, parent=self)
        if tooltip is not None:
            group_box.setToolTip(tooltip)
        group_box.layout().addLayout(self._rows_layout)
        group_box.layout().addWidget(self._add_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(group_box)
        self.setLayout(layout)

    def _append_row(self, item: ItemT) -> None:
        """Pure row construction. Never emits ``sig_update`` -- safe to call from ``set_data``."""
        row_editor = AttrsConfigEditor(
            title=self._item_title,
            factory_mapping=self._item_factory_mapping,
            config_type=self._item_type,
            save_load_buttons=False,
        )
        row_editor.set_data(item)
        row_editor.sig_update.connect(lambda _: self._emit_current_data())

        remove_button = QPushButton(icons.REMOVE(), "")
        remove_button.setToolTip("Remove this item")
        remove_button.setFlat(True)

        row_widget = QWidget()
        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(row_editor, stretch=1)
        row_layout.addWidget(remove_button, stretch=0)
        row_widget.setLayout(row_layout)

        self._rows_layout.addWidget(row_widget)
        self._rows.append((row_editor, remove_button, row_widget))

        remove_button.clicked.connect(lambda: self._on_user_remove(row_widget))

    def _remove_row_at(self, position: int) -> None:
        """Pure row teardown. Never emits ``sig_update`` -- safe to call from ``set_data``."""
        (_, _, row_widget) = self._rows.pop(position)
        self._rows_layout.removeWidget(row_widget)
        # Its slots may hold self's last reference; freeing self must not then destroy it as a child.
        row_widget.setParent(None)
        row_widget.deleteLater()

    def _on_add_clicked(self) -> None:
        self._append_row(self._make_default_item())
        self._emit_current_data()

    def _on_user_remove(self, row_widget: QWidget) -> None:
        position = next(i for i, (_, _, w) in enumerate(self._rows) if w is row_widget)
        self._remove_row_at(position)
        self._emit_current_data()

    def _emit_current_data(self) -> None:
        self.sig_update.emit(self.get_data())

    def set_data(self, value: t.Sequence[ItemT]) -> None:
        row_balance = len(self._rows) - len(value)

        if row_balance < 0:
            for _ in range(-row_balance):
                self._append_row(self._make_default_item())

        if row_balance > 0:
            for _ in range(row_balance):
                self._remove_row_at(len(self._rows) - 1)

        for item, (row_editor, _, _) in zip(value, self._rows):
            row_editor.set_data(item)

    def get_data(self) -> list[ItemT]:
        items: list[ItemT] = []
        for row_editor, _, _ in self._rows:
            item = row_editor.get_data()
            # A row's AttrsConfigEditor is only ever given a concrete item
            # (see _append_row/set_data), so it is never actually None.
            assert item is not None
            items.append(item)
        return items

    def handle_validation_results(
        self, validation_results: list[ValidationResult]
    ) -> list[ValidationResult]:
        not_handled = validation_results
        for row_editor, _, _ in self._rows:
            not_handled = row_editor.handle_validation_results(not_handled)
        return not_handled

    @property
    def is_ready(self) -> bool:
        return all(row_editor.is_ready for row_editor, _, _ in self._rows)
