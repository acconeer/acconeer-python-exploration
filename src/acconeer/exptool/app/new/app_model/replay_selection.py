# Copyright (c) Acconeer AB, 2024-2026
# All rights reserved
from __future__ import annotations

import typing as t
from pathlib import Path

import typing_extensions as te

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QRadioButton,
    QVBoxLayout,
)

from acconeer.exptool._core.entities.validation_result import ValidationResult
from acconeer.exptool.app.new.ui import DataEditor, MiscErrorView
from acconeer.exptool.app.new.ui.utils import ScrollAreaDecorator


_T = t.TypeVar("_T")
_PluginOptionT = t.TypeVar("_PluginOptionT", bound="_PluginOption")

_BODY_TEXT = """
<p>Select which plugin to be used for replaying the selected file.</p>
<p>
<b>Note!</b> Selecting plugins that is not <i>Sparse IQ</i> or annotated with
<i>(Used to record the file)</i> may not work.
</p>
"""

_LOADED_SOURCE_TEXT = """
<p>The configuration below is loaded from <code>{filename}</code>.</p>
<p>Feel free to make changes before replaying the file.</p>
"""
_DEFAULT_SOURCE_TEXT = """
<p>The configuration below is the default for the selected plugin.</p>
<p>Feel free to make changes before replaying the file.</p>
"""


class _PluginOption(te.Protocol):
    """Dependency Inversion interface for PluginSpec"""

    key: str
    title: str


class SelectPluginToReplayInDialog(QDialog, t.Generic[_PluginOptionT]):
    def __init__(
        self,
        plugin_options: t.Iterable[_PluginOptionT],
        default_selected: str,
        current_plugin_key: str | None,
        record_key: str | None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("File Load Plugin Selection")

        passed_plugin_keys = [po.key for po in plugin_options]
        if default_selected not in passed_plugin_keys:
            msg = f"{default_selected} needs to be one of {passed_plugin_keys}."
            raise ValueError(msg)

        label = QLabel(_BODY_TEXT)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)

        self.plugin_choice_buttons: dict[str, tuple[QRadioButton, _PluginOptionT]] = {}
        for po in plugin_options:
            if po.key == current_plugin_key == record_key:
                annotation = " (Current plugin, used to record the file)"
            elif po.key == current_plugin_key:
                annotation = " (Current plugin)"
            elif po.key == record_key:
                annotation = " (Used to record the file)"
            else:
                annotation = ""

            self.plugin_choice_buttons[po.key] = (QRadioButton(po.title + annotation), po)

        (default_button, _) = self.plugin_choice_buttons[default_selected]
        default_button.setChecked(True)

        self.button_group = QButtonGroup()
        for _, (btn, _) in self.plugin_choice_buttons.items():
            self.button_group.addButton(btn)

        self.dialog_buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Abort
        )
        self.dialog_buttons.accepted.connect(self.accept)
        self.dialog_buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(label)

        for _, (btn, _) in self.plugin_choice_buttons.items():
            layout.addWidget(btn)

        layout.addWidget(self.dialog_buttons)

        self.setLayout(layout)

    @property
    def selected_plugin_option(self) -> _PluginOptionT:
        checked_button = self.button_group.checkedButton()
        for key, (btn, po) in self.plugin_choice_buttons.items():
            if btn is checked_button:
                return po

        raise AssertionError


class EditConfigBeforeReplayDialog(QDialog):
    def __init__(
        self,
        data_editor: DataEditor[t.Any],
        source: te.Literal["default", "loaded"],
        source_file: Path,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Edit before replaying")

        if source == "loaded":
            label_text = _LOADED_SOURCE_TEXT.format(filename=source_file.name)
        elif source == "default":
            label_text = _DEFAULT_SOURCE_TEXT
        else:
            te.assert_never(source)

        self.misc_error_view = MiscErrorView(self)

        self.data_editor = data_editor

        label = QLabel(label_text)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)

        self.dialog_buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Abort
        )
        self.dialog_buttons.accepted.connect(self.accept)
        self.dialog_buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(label)
        layout.addWidget(self.misc_error_view)
        layout.addWidget(ScrollAreaDecorator(self.data_editor))
        layout.addWidget(self.dialog_buttons)

        self.setLayout(layout)
        # Without an explicit size, the dialog grows to fit ``data_editor``'s full
        # sizeHint and the scroll area never engages. Cap it to a sensible default
        # so configs with many parameters actually scroll instead of overflowing
        # the screen.
        avail = self.screen().availableGeometry()
        self.resize(min(600, int(avail.width() * 0.6)), min(700, int(avail.height() * 0.85)))

    def set_ok_enabled(self, enabled: bool) -> None:
        self.dialog_buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(enabled)

    def handle_validation_results(
        self, validation_results: list[ValidationResult]
    ) -> list[ValidationResult]:
        not_handled = self.data_editor.handle_validation_results(validation_results)
        not_handled = self.misc_error_view.handle_validation_results(not_handled)
        assert len(not_handled) == 0
        return []
