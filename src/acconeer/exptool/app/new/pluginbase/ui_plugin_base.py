# Copyright (c) Acconeer AB, 2024-2026
# All rights reserved
from __future__ import annotations

import logging

from PySide6.QtWidgets import QWidget

from acconeer.exptool.app.new.app_model.app_model import AppModel


_LOG = logging.getLogger(__name__)


class UiPluginBase(QWidget):
    def __init__(self, app_model: AppModel) -> None:
        super().__init__()
        self.__app_model = app_model
