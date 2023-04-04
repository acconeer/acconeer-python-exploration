# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QMainWindow

from acconeer.exptool.app.new.app_model import AppModel

from .misc import ExceptionWidget
from .status_bar import StatusBar
from .stream_tab import StreamingMainWidget


class MainWindow(QMainWindow):
    def __init__(self, app_model: AppModel) -> None:
        super().__init__()

        self.resize(1280, 720)

        self.setCentralWidget(StreamingMainWidget(app_model, self))
        self.setStatusBar(StatusBar(app_model, self))
        self.setWindowTitle("Acconeer Exploration Tool")
        self.moveEvent = lambda _: self.saveGeometry()

        app_model.sig_error.connect(self.on_app_model_error)

    def on_app_model_error(self, exception: Exception, traceback_str: Optional[str]) -> None:
        ExceptionWidget(self, exc=exception, traceback_str=traceback_str).exec()
