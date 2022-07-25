# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import abc
import logging
from typing import Generic, Type

import qtawesome as qta

from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from acconeer.exptool import a121
from acconeer.exptool.a121.algo._base import ConfigT
from acconeer.exptool.a121.algo._plugins._a121 import A121ViewPluginBase
from acconeer.exptool.app.new import (
    BUTTON_ICON_COLOR,
    AppModel,
    ConnectionState,
    GeneralMessage,
    PluginState,
)
from acconeer.exptool.app.new.ui.plugin import (
    AttrsConfigEditor,
    GridGroupBox,
    PidgetFactoryMapping,
    SessionConfigEditor,
    SmartMetadataView,
    SmartPerfCalcView,
)

from .backend_plugin import ProcessorBackendPluginSharedState


log = logging.getLogger(__name__)


class ProcessorViewPluginBase(Generic[ConfigT], A121ViewPluginBase):
    def __init__(self, view_widget: QWidget, app_model: AppModel) -> None:
        super().__init__(app_model=app_model, view_widget=view_widget)
        self.layout = QVBoxLayout(self.view_widget)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.view_widget.setLayout(self.layout)

        self.start_button = QPushButton(
            qta.icon("fa5s.play-circle", color=BUTTON_ICON_COLOR),
            "Start measurement",
            self.view_widget,
        )
        self.stop_button = QPushButton(
            qta.icon("fa5s.stop-circle", color=BUTTON_ICON_COLOR),
            "Stop",
            self.view_widget,
        )
        self.defaults_button = QPushButton(
            qta.icon("mdi6.restore", color=BUTTON_ICON_COLOR),
            "Restore default settings",
            self.view_widget,
        )
        self.start_button.clicked.connect(self._send_start_requests)
        self.stop_button.clicked.connect(self._send_stop_requests)
        self.defaults_button.clicked.connect(self._send_defaults_request)

        self.start_button.setShortcut("space")
        self.stop_button.setShortcut("space")

        button_group = GridGroupBox("Controls", parent=self.view_widget)
        button_group.layout().addWidget(self.start_button, 0, 0)
        button_group.layout().addWidget(self.stop_button, 0, 1)
        button_group.layout().addWidget(self.defaults_button, 1, 0, 1, 2)

        self.layout.addWidget(button_group)

        self.metadata_view = SmartMetadataView(self.view_widget)
        self.layout.addWidget(self.metadata_view)

        self.perf_calc_view = SmartPerfCalcView(self.view_widget)
        self.layout.addWidget(self.perf_calc_view)

        self.session_config_editor = SessionConfigEditor(self.view_widget)
        self.session_config_editor.sig_update.connect(self._on_session_config_update)
        self.processor_config_editor = AttrsConfigEditor[ConfigT](
            title="Processor parameters",
            factory_mapping=self.get_pidget_mapping(),
            parent=self.view_widget,
        )
        self.processor_config_editor.sig_update.connect(self._on_processor_config_update)
        self.layout.addWidget(self.processor_config_editor)
        self.layout.addWidget(self.session_config_editor)
        self.layout.addStretch()

    def _on_session_config_update(self, session_config: a121.SessionConfig) -> None:
        self.app_model.put_backend_plugin_task(
            "update_session_config", {"session_config": session_config}
        )

    def _on_processor_config_update(self, processor_config: ConfigT) -> None:
        self.app_model.put_backend_plugin_task(
            "update_processor_config", {"processor_config": processor_config}
        )

    def _send_start_requests(self) -> None:
        self.app_model.put_backend_plugin_task("start_session", on_error=self.app_model.emit_error)
        self.app_model.set_plugin_state(PluginState.LOADED_STARTING)

    def _send_stop_requests(self) -> None:
        self.app_model.put_backend_plugin_task("stop_session", on_error=self.app_model.emit_error)
        self.app_model.set_plugin_state(PluginState.LOADED_STOPPING)

    def _send_defaults_request(self) -> None:
        self.app_model.put_backend_plugin_task("restore_defaults")

    def teardown(self) -> None:
        self.layout.deleteLater()

    def handle_message(self, message: GeneralMessage) -> None:
        if message.name == "sync":
            log.debug(f"{type(self).__name__} syncing")

            self.session_config_editor.sync()
            self.processor_config_editor.sync()
        else:
            raise RuntimeError("Unknown message")

    def on_app_model_update(self, app_model: AppModel) -> None:
        self.session_config_editor.setEnabled(app_model.plugin_state == PluginState.LOADED_IDLE)
        self.processor_config_editor.setEnabled(app_model.plugin_state == PluginState.LOADED_IDLE)
        self.start_button.setEnabled(
            app_model.plugin_state == PluginState.LOADED_IDLE
            and app_model.connection_state == ConnectionState.CONNECTED
            and app_model.backend_plugin_state.ready
        )
        self.stop_button.setEnabled(app_model.plugin_state == PluginState.LOADED_BUSY)
        self.defaults_button.setEnabled(app_model.plugin_state == PluginState.LOADED_IDLE)

        if app_model.backend_plugin_state is None:
            self.session_config_editor.set_data(None)
            self.processor_config_editor.set_data(None)
            self.metadata_view.update(None)
            self.perf_calc_view.update()
        else:
            assert isinstance(app_model.backend_plugin_state, ProcessorBackendPluginSharedState)
            assert isinstance(
                app_model.backend_plugin_state.processor_config, self.get_processor_config_cls()
            )

            self.session_config_editor.set_data(app_model.backend_plugin_state.session_config)
            self.processor_config_editor.set_data(app_model.backend_plugin_state.processor_config)
            self.metadata_view.update(app_model.backend_plugin_state.metadata)
            self.perf_calc_view.update(
                app_model.backend_plugin_state.session_config,
                app_model.backend_plugin_state.metadata,
            )

        self.session_config_editor.update_available_sensor_list(app_model._a121_server_info)

    @classmethod
    @abc.abstractmethod
    def get_pidget_mapping(cls) -> PidgetFactoryMapping:
        pass

    @classmethod
    @abc.abstractmethod
    def get_processor_config_cls(cls) -> Type[ConfigT]:
        pass
