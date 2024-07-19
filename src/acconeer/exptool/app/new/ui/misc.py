# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved

from __future__ import annotations

import contextlib
import logging
import traceback
from typing import Iterator, Optional

import pyperclip

from PySide6 import QtGui
from PySide6.QtWidgets import QFrame, QHBoxLayout, QMessageBox, QPushButton, QWidget

from acconeer.exptool.app.new._exceptions import HandledException


_LOG = logging.getLogger(__name__)


class ExceptionWidget(QMessageBox):
    def __init__(
        self,
        parent: Optional[QWidget],
        *,
        exc: Exception,
        traceback_str: Optional[str] = None,
        title: str = "Error",
    ) -> None:
        super().__init__(parent)

        self.setIcon(QMessageBox.Icon.Warning)
        self.setStandardButtons(QMessageBox.StandardButton.Ok)

        self.setWindowTitle(title)
        self.setText(str(exc))

        try:
            raise exc
        except HandledException:
            pass
        except Exception:
            self.setInformativeText("<b>Unhandled error - please file a bug</b>")

        if traceback_str:
            self.setDetailedText(traceback_str)
            copy_button = QPushButton(self)
            copy_button.setText("Copy details")
            self.addButton(copy_button, QMessageBox.ButtonRole.ActionRole)
            copy_button.clicked.disconnect()
            copy_button.clicked.connect(self._on_copy_clicked)

    @classmethod
    @contextlib.contextmanager
    def context(cls) -> Iterator[None]:
        try:
            yield
        except Exception as e:
            _LOG.debug("Exception raised in MainThread:", exc_info=True)
            cls(parent=None, exc=e, traceback_str=traceback.format_exc()).exec()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self.setFixedWidth(500)

    def _on_copy_clicked(self) -> None:
        detailed_text = self.detailedText()
        if detailed_text:
            pyperclip.copy(detailed_text)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self.close()


class VerticalSeparator(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)

        self.setLayout(QHBoxLayout(self))
        self.layout().setContentsMargins(5, 5, 5, 5)

        frame = QFrame(self)
        frame.setFrameShape(QFrame.Shape.VLine)
        self.layout().addWidget(frame)
