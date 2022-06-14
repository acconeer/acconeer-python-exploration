from __future__ import annotations

from PySide6 import QtGui
from PySide6.QtWidgets import QMessageBox, QWidget


class ExceptionWidget(QMessageBox):
    def __init__(self, parent: QWidget, *, exc: Exception, title: str = "Error") -> None:
        super().__init__(parent)

        self.setIcon(QMessageBox.Warning)
        self.setStandardButtons(QMessageBox.Ok)

        self.setWindowTitle(title)
        self.setText(str(exc))

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self.setFixedWidth(500)
