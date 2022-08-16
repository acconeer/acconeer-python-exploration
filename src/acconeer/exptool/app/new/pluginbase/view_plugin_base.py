# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import abc

from PySide6.QtWidgets import QWidget

from acconeer.exptool.app.new.app_model import AppModel, AppModelListener, ViewPluginInterface
from acconeer.exptool.app.new.backend import GeneralMessage


class ViewPluginBase(AppModelListener, abc.ABC, ViewPluginInterface):
    def __init__(self, app_model: AppModel, view_widget: QWidget) -> None:
        super().__init__(app_model)
        self.view_widget = view_widget
        app_model.sig_message_view_plugin.connect(self.handle_message)

    @abc.abstractmethod
    def handle_message(self, message: GeneralMessage) -> None:
        pass
