# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from acconeer.exptool.app.new.app_model import AppModel


class AppModelAwareWidget(QWidget):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)
        app_model.sig_notify.connect(self.on_app_model_update)

    def on_app_model_update(self, app_model: AppModel) -> None:
        pass
