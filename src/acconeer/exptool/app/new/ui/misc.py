# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import abc
import platform
import webbrowser
from typing import List, Optional

import pyperclip
import qtawesome as qta

from PySide6 import QtCore, QtGui
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QWidget,
)

from acconeer.exptool.app.new._enums import ConnectionInterface
from acconeer.exptool.app.new._exceptions import HandledException
from acconeer.exptool.app.new.app_model import AppModel
from acconeer.exptool.utils import CommDevice  # type: ignore[import]


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
            copy_button = QPushButton(self)
            copy_button.setText("Copy details")
            self.addButton(copy_button, QMessageBox.ButtonRole.ActionRole)
            copy_button.clicked.disconnect()
            copy_button.clicked.connect(self._on_copy_clicked)

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
        frame.setFrameShape(QFrame.VLine)
        self.layout().addWidget(frame)


class CommDeviceComboBox(QComboBox):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)
        self.app_model = app_model
        app_model.sig_notify.connect(self._on_app_model_update)
        self.currentTextChanged.connect(self._on_change)
        self.setMinimumWidth(175)

    def _on_app_model_update(self, app_model: AppModel) -> None:
        devices = self._get_available_devices()

        view_ports = [self.itemData(i) for i in range(self.count())]

        with QtCore.QSignalBlocker(self):
            if devices != view_ports:
                self.clear()
                for device in devices:
                    self.addItem(device.display_name(), device)

            current_device = self._get_current_device()

            # QComboBox.findData can't be used since since it doesn't
            # always match different but content wise identical objects.
            index = -1
            for i in range(self.count()):
                if self.itemData(i) == current_device:
                    index = i
                    break
            self.setCurrentIndex(index)

            self.setEnabled(self.count() > 0)
            if self.count() == 0:
                self.addItem("No device available")

    @abc.abstractmethod
    def _on_change(self) -> None:
        pass

    @abc.abstractmethod
    def _get_available_devices(self) -> List[CommDevice]:
        pass

    @abc.abstractmethod
    def _get_current_device(self) -> Optional[CommDevice]:
        pass


class SerialPortComboBox(CommDeviceComboBox):
    def _on_change(self) -> None:
        self.app_model.set_serial_connection_device(self.currentData())

    def _get_available_devices(self) -> List[CommDevice]:
        return self.app_model.available_serial_devices

    def _get_current_device(self) -> Optional[CommDevice]:
        return self.app_model.serial_connection_device


class USBDeviceComboBox(CommDeviceComboBox):
    def _on_change(self) -> None:
        self.app_model.set_usb_connection_device(self.currentData())

    def _get_available_devices(self) -> List[CommDevice]:
        return self.app_model.available_usb_devices

    def _get_current_device(self) -> Optional[CommDevice]:
        return self.app_model.usb_connection_device


class HintObject:
    def __init__(self, warning: str, tooltip: str, how_to_fix_url: str) -> None:
        self.warning = warning
        self.tooltip = tooltip
        self.how_to_fix_url = how_to_fix_url

    @staticmethod
    @abc.abstractmethod
    def _should_show(app_model: AppModel) -> bool:
        pass


class UserHintWidget(QWidget):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)
        app_model.sig_notify.connect(self._on_app_model_update)

        self._hints: List[HintObject] = []
        self._how_to_fix_url: Optional[str] = None

        self.setLayout(QHBoxLayout(self))
        self.layout().setContentsMargins(0, 0, 0, 0)

        self.icon = qta.IconWidget()
        self.icon.setHidden(True)
        self.icon.setIcon(qta.icon("fa.warning", color="#ff9e00"))
        self.layout().addWidget(self.icon)

        self.label = QLabel(self)
        self.label.setHidden(True)
        self.layout().addWidget(self.label)

        self.button = QPushButton(self)
        self.button.setIcon(qta.icon("fa5s.external-link-alt", color=BUTTON_ICON_COLOR))
        self.button.setText("How to fix")
        self.button.clicked.connect(self._on_click)
        self.button.setHidden(True)
        self.layout().addWidget(self.button)

    def add_hint(self, hint: HintObject) -> None:
        self._hints.append(hint)

    def _on_app_model_update(self, app_model: AppModel) -> None:
        for hint in self._hints:
            if hint._should_show(app_model):
                self.label.setText(hint.warning)
                self.label.setToolTip(hint.tooltip)
                self.icon.setToolTip(hint.tooltip)
                self._how_to_fix_url = hint.how_to_fix_url
                self.icon.setHidden(False)
                self.label.setHidden(False)
                if self._how_to_fix_url is not None:
                    self.button.setHidden(False)
                return

        self.icon.setHidden(True)
        self.label.setHidden(True)
        self.button.setHidden(True)

    def _on_click(self) -> None:
        if self._how_to_fix_url is not None:
            webbrowser.open_new_tab(self._how_to_fix_url)


class ConnectionHint(HintObject):
    def __init__(self) -> None:
        super().__init__(
            "Stability warning",
            "You may experience stability issues due to windows serial port driver",
            r"https://docs.acconeer.com/en/latest/evk_setup/xc120_xe121.html",
        )

    @staticmethod
    def _should_show(app_model: AppModel) -> bool:
        if platform.system().lower() != "windows":
            return False

        if (
            app_model.serial_connection_device is not None
            and app_model.connection_interface == ConnectionInterface.SERIAL
        ):
            if app_model.serial_connection_device.name is not None:
                if app_model.serial_connection_device.unflashed:
                    return False
                return "xc120" in app_model.serial_connection_device.name.lower()

        return False


class UnflashedDeviceHint(HintObject):
    def __init__(self) -> None:
        super().__init__(
            "Unflashed device",
            "The device needs to be flashed with exploration server firmware",
            r"https://docs.acconeer.com/en/latest/evk_setup/xc120_xe121.html",
        )

    @staticmethod
    def _should_show(app_model: AppModel) -> bool:
        if app_model.connection_interface not in [
            ConnectionInterface.SERIAL,
            ConnectionInterface.USB,
        ]:
            return False

        if (
            app_model.serial_connection_device is not None
            and app_model.connection_interface == ConnectionInterface.SERIAL
            and app_model.serial_connection_device.unflashed
        ):
            return True

        if (
            app_model.usb_connection_device is not None
            and app_model.connection_interface == ConnectionInterface.USB
            and app_model.usb_connection_device.unflashed
        ):
            return True

        return False


class InaccessibleDeviceHint(HintObject):
    def __init__(self) -> None:
        super().__init__(
            "Device permissions",
            "The USB device permissions needs to be setup, "
            "update USB permissions or use Serial Port",
            r"https://docs.acconeer.com/en/latest/exploration_tool/"
            "installation_and_setup.html#linux-setup",
        )

    @staticmethod
    def _should_show(app_model: AppModel) -> bool:
        if (
            app_model.usb_connection_device is not None
            and app_model.connection_interface == ConnectionInterface.USB
            and not app_model.usb_connection_device.accessible
        ):
            return True

        return False


class HintWidget(QWidget):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)
        self.setLayout(QHBoxLayout(self))
        self.layout().setContentsMargins(0, 0, 0, 0)

        hint_widget = UserHintWidget(app_model, self)
        self.layout().addWidget(hint_widget)

        # Prioritized hint order:
        # The first will have priority over the second
        # The second will have priority over the third...
        hint_widget.add_hint(InaccessibleDeviceHint())
        hint_widget.add_hint(UnflashedDeviceHint())
        hint_widget.add_hint(ConnectionHint())
