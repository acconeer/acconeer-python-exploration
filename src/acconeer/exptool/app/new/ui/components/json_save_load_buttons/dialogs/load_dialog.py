# Copyright (c) Acconeer AB, 2023
# All rights reserved
from __future__ import annotations

import typing as t
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .syntax_highlight import SyntaxHighlighter


class _JsonEditor(QWidget):
    def __init__(self, submit_slot: t.Callable[[str], t.Any]) -> None:
        super().__init__()

        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("Input JSON here")
        self.text_edit.setFontFamily("monospace")
        self._syntax_highlight = SyntaxHighlighter.json(self.text_edit.document())

        self.load_button = QPushButton("Load JSON")
        self.load_button.clicked.connect(lambda: submit_slot(self.text_edit.toPlainText()))

        layout = QVBoxLayout()
        layout.addWidget(self.text_edit, stretch=1)
        layout.addWidget(self.load_button, stretch=0)
        self.setLayout(layout)


class LoadDialogWithJsonEditor(QDialog):
    def __init__(
        self,
        dialog: QFileDialog,
        parent: t.Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent=parent)

        self._contents: t.Optional[str] = None

        self._dialog = dialog
        self._dialog.accepted.connect(self._set_selected_file_contents)
        self._dialog.rejected.connect(self.reject)

        layout = QHBoxLayout()
        layout.addWidget(self._dialog, stretch=1)
        layout.addWidget(
            _JsonEditor(self._set_contents),
            stretch=1,
        )
        self.setLayout(layout)

    def _set_selected_file_contents(self) -> None:
        """Handles the "Open" button being pressed in the dialog"""
        (selected_file,) = self._dialog.selectedFiles()
        self._contents = Path(selected_file).read_text()
        self.accept()

    def _set_contents(self, contents: str) -> None:
        """Handles the submitted content from _JsonEditor."""
        self._contents = contents
        self.accept()

    @classmethod
    def get_load_contents(
        cls,
        caption: str = "",
        filter: str = "All (*)",
        options: QFileDialog.Option = QFileDialog.Option.DontUseNativeDialog,
        parent: t.Optional[QWidget] = None,
    ) -> t.Optional[str]:
        dialog = QFileDialog(caption=caption)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        dialog.setNameFilter(filter)
        dialog.setOptions(options)

        instance = cls(dialog, parent=parent)
        if instance.exec():
            return instance._contents
        else:
            return None
