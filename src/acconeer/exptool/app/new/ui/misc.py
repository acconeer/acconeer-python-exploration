from __future__ import annotations

from typing import Optional

from PySide6 import QtGui
from PySide6.QtWidgets import QFrame, QHBoxLayout, QMessageBox, QWidget


class ExceptionWidget(QMessageBox):
    def __init__(
        self,
        parent: QWidget,
        *,
        exc: Exception,
        traceback_str: Optional[str] = None,
        title: str = "Error",
    ) -> None:
        super().__init__(parent)

        self.setIcon(QMessageBox.Warning)
        self.setStandardButtons(QMessageBox.Ok)

        self.setWindowTitle(title)
        self.setText(str(exc))

        if traceback_str:
            self.setDetailedText(traceback_str)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self.setFixedWidth(500)


class VerticalSeparator(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)

        self.setLayout(QHBoxLayout(self))
        self.layout().setContentsMargins(5, 5, 5, 5)

        frame = QFrame(self)
        frame.setFrameShape(QFrame.VLine)
        self.layout().addWidget(frame)
