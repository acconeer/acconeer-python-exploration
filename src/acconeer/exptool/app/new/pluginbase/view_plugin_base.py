# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import typing as t

from PySide6.QtWidgets import QVBoxLayout, QWidget

from acconeer.exptool.app.new.app_model import AppModel
from acconeer.exptool.app.new.ui import utils


class ViewPluginBase:
    def __init__(self, app_model: AppModel, view_widget: QWidget) -> None:
        self.app_model = app_model

        self.app_model.sig_notify.connect(self.on_app_model_update)
        self.app_model.sig_backend_state_changed.connect(self.on_backend_state_update)
        self.app_model.sig_load_plugin.connect(self.on_load_plugin)

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

    def on_load_plugin(self, plugin_spec: t.Optional[t.Any]) -> None:
        if plugin_spec is None:
            self.app_model.sig_notify.disconnect(self.on_app_model_update)
            self.app_model.sig_backend_state_changed.disconnect(self.on_backend_state_update)
            self.app_model.sig_load_plugin.disconnect(self.on_load_plugin)

    def on_app_model_update(self, app_model: AppModel) -> None:
        pass

    def on_backend_state_update(self, state: t.Optional[t.Any]) -> None:
        pass

    @property
    def sticky_widget(self) -> QWidget:
        """The sticky widget. The sticky area is located at the top."""
        return self._sticky_widget

    @property
    def scrolly_widget(self) -> QWidget:
        """The scrolly widget. The scrolly area is located below the sticky area"""
        return self._scrolly_widget
