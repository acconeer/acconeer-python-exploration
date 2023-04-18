# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import logging

from PySide6.QtWidgets import QPushButton, QWidget

from acconeer.exptool.app.new._enums import ConnectionState
from acconeer.exptool.app.new.app_model import AppModel
from acconeer.exptool.app.new.ui.icons import FLASH

from .dialogs import FlashPopup


log = logging.getLogger(__name__)


class FlashButton(QPushButton):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.app_model = app_model

        self.setFixedWidth(100)
        self.setText("Flash")
        self.setIcon(FLASH())
        self.setToolTip("Flash the device with a bin file")

        app_model.sig_notify.connect(self._on_app_model_update)
        self.pop_up = FlashPopup(app_model, self)
        self.clicked.connect(self._on_click)

    def _on_click(self) -> None:
        self.pop_up.exec()

    def _on_app_model_update(self, app_model: AppModel) -> None:
        self.setEnabled(app_model.connection_state == ConnectionState.DISCONNECTED)
