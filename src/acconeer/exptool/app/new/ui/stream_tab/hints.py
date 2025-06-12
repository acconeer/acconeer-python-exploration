# Copyright (c) Acconeer AB, 2023-2025
# All rights reserved

from __future__ import annotations

import abc
import webbrowser
from typing import List, Optional

import qtawesome as qta

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from acconeer.exptool.app.new._enums import ConnectionInterface
from acconeer.exptool.app.new.app_model import AppModel
from acconeer.exptool.app.new.ui.icons import EXTERNAL_LINK, WARNING


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

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.icon = qta.IconWidget()
        self.icon.setHidden(True)
        self.icon.setIcon(WARNING())
        layout.addWidget(self.icon)

        self.label = QLabel(self)
        self.label.setHidden(True)
        layout.addWidget(self.label)

        self.button = QPushButton(self)
        self.button.setIcon(EXTERNAL_LINK())
        self.button.setText("How to fix")
        self.button.clicked.connect(self._on_click)
        self.button.setHidden(True)
        layout.addWidget(self.button)

        self.setLayout(layout)

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

        return (
            app_model.usb_connection_device is not None
            and app_model.connection_interface == ConnectionInterface.USB
            and app_model.usb_connection_device.unflashed
        )


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
        return (
            app_model.usb_connection_device is not None
            and app_model.connection_interface == ConnectionInterface.USB
            and not app_model.usb_connection_device.accessible
        )


class HintWidget(QWidget):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        hint_widget = UserHintWidget(app_model, self)
        layout.addWidget(hint_widget)

        # Prioritized hint order:
        # The first will have priority over the second
        # The second will have priority over the third...
        hint_widget.add_hint(InaccessibleDeviceHint())
        hint_widget.add_hint(UnflashedDeviceHint())

        self.setLayout(layout)
