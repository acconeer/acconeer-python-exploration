# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import abc

from PySide6.QtWidgets import QVBoxLayout, QWidget

from acconeer.exptool.app.new import PluginState
from acconeer.exptool.app.new.app_model import AppModel, ViewPluginInterface
from acconeer.exptool.app.new.backend import GeneralMessage
from acconeer.exptool.app.new.ui import utils

from .ui_plugin_base import UiPluginBase


class ViewPluginBase(UiPluginBase, abc.ABC, ViewPluginInterface):
    def __init__(self, app_model: AppModel, view_widget: QWidget) -> None:
        super().__init__(app_model)
        self.app_model = app_model
        self.app_model.sig_message_view_plugin.connect(self.handle_message)

        self.__view_widget = view_widget
        self.__view_widget.setLayout(QVBoxLayout())

        self._sticky_widget = QWidget()
        self._scrolly_widget = QWidget()

        self.__view_widget.layout().addWidget(self._sticky_widget)
        self.__view_widget.layout().addWidget(utils.HorizontalSeparator())
        self.__view_widget.layout().addWidget(
            utils.ScrollAreaDecorator(
                utils.TopAlignDecorator(
                    self._scrolly_widget,
                )
            )
        )

    def stop_listening(self) -> None:
        super().stop_listening()
        self.app_model.sig_message_view_plugin.disconnect(self.handle_message)

    @property
    def sticky_widget(self) -> QWidget:
        """The sticky widget. The sticky area is located at the top."""
        return self._sticky_widget

    @property
    def scrolly_widget(self) -> QWidget:
        """The scrolly widget. The scrolly area is located below the sticky area"""
        return self._scrolly_widget

    @abc.abstractmethod
    def handle_message(self, message: GeneralMessage) -> None:
        pass

    def _send_start_request(self) -> None:
        self.app_model.put_backend_plugin_task(
            "start_session",
            {"with_recorder": self.app_model.recording_enabled},
            on_error=self.app_model.emit_error,
        )
        self.app_model.set_plugin_state(PluginState.LOADED_STARTING)

    def _send_stop_request(self) -> None:
        self.app_model.put_backend_plugin_task("stop_session", on_error=self.app_model.emit_error)
        self.app_model.set_plugin_state(PluginState.LOADED_STOPPING)
