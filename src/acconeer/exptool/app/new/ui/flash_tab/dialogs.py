# Copyright (c) Acconeer AB, 2022-2025
# All rights reserved

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QPushButton,
    QTextEdit,
    QWidget,
)


_WRONG_CREDENTIALS_MSG = "<font color='red'>Incorrect username (email) or password</font>"

log = logging.getLogger(__name__)


class UserMessageDialog(QDialog):
    def __init__(
        self,
        title: str,
        message: Optional[str],
        confirmation: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self.setMinimumWidth(450)
        self.setMinimumHeight(200)

        layout = QGridLayout(self)

        self.message_text = QTextEdit(self)
        self.message_text.setReadOnly(True)

        self.ok_button = QPushButton(confirmation, self)
        self.ok_button.setEnabled(True)
        self.ok_button.clicked.connect(self._on_ok)

        # fmt: off
        # Grid layout:                      row, col, rspan, cspan
        layout.addWidget(self.message_text, 0,   0,   4,     12)    # noqa: E241
        layout.addWidget(self.ok_button,    4,   0,   1,     2)     # noqa: E241
        # fmt: on

        self.setLayout(layout)

        self.setWindowTitle(title)
        if message is not None:
            self.set_message(message)

    def set_message(self, message: str) -> None:
        self.message_text.clear()
        self.message_text.insertHtml(message)
        self.message_text.moveCursor(QTextCursor.MoveOperation.Start)

    def _on_ok(self) -> None:
        self.accept()
