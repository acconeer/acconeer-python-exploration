# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import abc
import logging
from typing import Generic, Optional, Type

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
from acconeer.exptool.app.new.ui.plugin_components import (
    AttrsConfigEditor,
    GridGroupBox,
    PidgetFactoryMapping,
    SessionConfigEditor,
    SmartMetadataView,
    SmartPerfCalcView,
)

from .backend_plugin import ProcessorBackendPluginSharedState


log = logging.getLogger(__name__)


class ProcessorViewPluginBase(A121ViewPluginBase, Generic[ConfigT]):
    def __init__(self, app_model: AppModel, view_widget: QWidget) -> None:
        super().__init__(app_model=app_model, view_widget=view_widget)
        self.app_model = app_model

        sticky_layout = QVBoxLayout()
        sticky_layout.setContentsMargins(0, 0, 0, 0)
        scrolly_layout = QVBoxLayout()
        scrolly_layout.setContentsMargins(0, 0, 0, 0)

        self.start_button = QPushButton(
            qta.icon("fa5s.play-circle", color=BUTTON_ICON_COLOR),
            "Start measurement",
            self.sticky_widget,
        )
        self.stop_button = QPushButton(
            qta.icon("fa5s.stop-circle", color=BUTTON_ICON_COLOR),
            "Stop",
            self.sticky_widget,
        )
        self.defaults_button = QPushButton(
            qta.icon("mdi6.restore", color=BUTTON_ICON_COLOR),
            "Restore default settings",
            self.sticky_widget,
        )
        self.start_button.clicked.connect(self._send_start_requests)
        self.stop_button.clicked.connect(self._send_stop_requests)
        self.defaults_button.clicked.connect(self._send_defaults_request)

        self.start_button.setShortcut("space")
        self.start_button.setToolTip("Starts the session.\n\nShortcut: Space")
        self.stop_button.setShortcut("space")
        self.stop_button.setToolTip("Stops the session.\n\nShortcut: Space")

        button_group = GridGroupBox("Controls", parent=self.sticky_widget)
        button_group.layout().addWidget(self.start_button, 0, 0)
        button_group.layout().addWidget(self.stop_button, 0, 1)
        button_group.layout().addWidget(self.defaults_button, 1, 0, 1, 2)
        sticky_layout.addWidget(button_group)

        self.metadata_view = SmartMetadataView(parent=self.scrolly_widget)
        scrolly_layout.addWidget(self.metadata_view)

        self.perf_calc_view = SmartPerfCalcView(parent=self.scrolly_widget)
        scrolly_layout.addWidget(self.perf_calc_view)

        self.processor_config_editor = AttrsConfigEditor[ConfigT](
            title="Processor parameters",
            factory_mapping=self.get_pidget_mapping(),
            parent=self.scrolly_widget,
        )
        self.processor_config_editor.sig_update.connect(self._on_processor_config_update)
        scrolly_layout.addWidget(self.processor_config_editor)

        self.session_config_editor = SessionConfigEditor(
            self.supports_multiple_subsweeps(), self.scrolly_widget
        )
        self.session_config_editor.sig_update.connect(self._on_session_config_update)
        scrolly_layout.addWidget(self.session_config_editor)

        self.sticky_widget.setLayout(sticky_layout)
        self.scrolly_widget.setLayout(scrolly_layout)

    def _on_session_config_update(self, session_config: a121.SessionConfig) -> None:
        self.app_model.put_backend_plugin_task(
            "update_session_config", {"session_config": session_config}
        )

    def _on_processor_config_update(self, processor_config: ConfigT) -> None:
        self.app_model.put_backend_plugin_task(
            "update_processor_config", {"processor_config": processor_config}
        )

    def _send_start_requests(self) -> None:
        self.app_model.put_backend_plugin_task(
            "start_session",
            {"with_recorder": self.app_model.recording_enabled},
            on_error=self.app_model.emit_error,
        )
        self.app_model.set_plugin_state(PluginState.LOADED_STARTING)

    def _send_stop_requests(self) -> None:
        self.app_model.put_backend_plugin_task("stop_session", on_error=self.app_model.emit_error)
        self.app_model.set_plugin_state(PluginState.LOADED_STOPPING)

    def _send_defaults_request(self) -> None:
        self.app_model.put_backend_plugin_task("restore_defaults")

    def handle_message(self, message: GeneralMessage) -> None:
        if message.name == "sync":
            log.debug(f"{type(self).__name__} syncing")

            self.session_config_editor.sync()
            self.processor_config_editor.sync()
        else:
            raise RuntimeError("Unknown message")

    def on_backend_state_update(
        self, backend_plugin_state: Optional[ProcessorBackendPluginSharedState]
    ) -> None:
        if backend_plugin_state is None:
            self.session_config_editor.set_data(None)
            self.processor_config_editor.set_data(None)
            self.metadata_view.update(None)
            self.perf_calc_view.update()
        else:
            assert isinstance(backend_plugin_state, ProcessorBackendPluginSharedState)
            assert isinstance(
                backend_plugin_state.processor_config, self.get_processor_config_cls()
            )

            self.session_config_editor.set_data(backend_plugin_state.session_config)
            self.processor_config_editor.set_data(backend_plugin_state.processor_config)
            self.metadata_view.update(backend_plugin_state.metadata)
            self.perf_calc_view.update(
                backend_plugin_state.session_config,
                backend_plugin_state.metadata,
            )

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
        self.session_config_editor.update_available_sensor_list(app_model._a121_server_info)

    @classmethod
    def supports_multiple_subsweeps(self) -> bool:
        return False

    @classmethod
    @abc.abstractmethod
    def get_pidget_mapping(cls) -> PidgetFactoryMapping:
        pass

    @classmethod
    @abc.abstractmethod
    def get_processor_config_cls(cls) -> Type[ConfigT]:
        pass
