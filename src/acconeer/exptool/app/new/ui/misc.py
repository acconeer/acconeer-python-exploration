from __future__ import annotations

from typing import Optional

from PySide6 import QtCore, QtGui
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QMessageBox, QWidget

from acconeer.exptool.app.new._exceptions import HandledException
from acconeer.exptool.app.new.app_model import AppModel


BUTTON_ICON_COLOR = "#0081db"


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

        try:
            raise exc
        except HandledException:
            pass
        except Exception:
            self.setInformativeText("<b>Unhandled error - please file a bug</b>")

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


class SerialPortComboBox(QComboBox):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)
        self.app_model = app_model
        app_model.sig_notify.connect(self._on_app_model_update)
        self.currentTextChanged.connect(self._on_change)

    def _on_change(self) -> None:
        self.app_model.set_serial_connection_port(self.currentData())

    def _on_app_model_update(self, app_model: AppModel) -> None:
        tagged_ports = app_model.available_tagged_ports

        ports = [port for port, _ in tagged_ports]
        view_ports = [self.itemData(i) for i in range(self.count())]

        with QtCore.QSignalBlocker(self):
            if ports != view_ports:
                self.clear()
                for port, tag in tagged_ports:
                    label = port if tag is None else f"{port} ({tag})"
                    self.addItem(label, port)

            index = self.findData(app_model.serial_connection_port)
            self.setCurrentIndex(index)
