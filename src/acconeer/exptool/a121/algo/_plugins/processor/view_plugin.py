# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import abc
import logging
from typing import Generic, Optional, Type

import qtawesome as qta

from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from acconeer.exptool import a121
from acconeer.exptool.a121.algo._base import ProcessorConfigT
from acconeer.exptool.a121.algo._plugins._a121 import A121ViewPluginBase
from acconeer.exptool.app.new import (
    BUTTON_ICON_COLOR,
    AppModel,
    AttrsConfigEditor,
    GeneralMessage,
    GridGroupBox,
    MiscErrorView,
    PidgetFactoryMapping,
    PluginState,
    SessionConfigEditor,
    SmartMetadataView,
    SmartPerfCalcView,
)

from .backend_plugin import ProcessorBackendPluginSharedState


log = logging.getLogger(__name__)


class ProcessorViewPluginBase(A121ViewPluginBase, Generic[ProcessorConfigT]):
    def __init__(self, app_model: AppModel, view_widget: QWidget) -> None:
        super().__init__(app_model=app_model, view_widget=view_widget)

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
        self.start_button.clicked.connect(self._send_start_request)
        self.stop_button.clicked.connect(self._send_stop_request)

        self.start_button.setShortcut("space")
        self.start_button.setToolTip("Starts the session.\n\nShortcut: Space")
        self.stop_button.setShortcut("space")
        self.stop_button.setToolTip("Stops the session.\n\nShortcut: Space")

        button_group = GridGroupBox("Controls", parent=self.sticky_widget)
        button_group.layout().addWidget(self.start_button, 0, 0)
        button_group.layout().addWidget(self.stop_button, 0, 1)
        sticky_layout.addWidget(button_group)

        self.metadata_view = SmartMetadataView(parent=self.scrolly_widget)
        scrolly_layout.addWidget(self.metadata_view)

        self.perf_calc_view = SmartPerfCalcView(parent=self.scrolly_widget)
        scrolly_layout.addWidget(self.perf_calc_view)

        self.processor_config_editor = AttrsConfigEditor[ProcessorConfigT](
            title="Processor parameters",
            factory_mapping=self.get_pidget_mapping(),
            parent=self.scrolly_widget,
        )
        self.processor_config_editor.sig_update.connect(self._on_processor_config_update)
        scrolly_layout.addWidget(self.processor_config_editor)

        self.misc_error_view = MiscErrorView(self.scrolly_widget)
        scrolly_layout.addWidget(self.misc_error_view)

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

    def _on_processor_config_update(self, processor_config: ProcessorConfigT) -> None:
        self.app_model.put_backend_plugin_task(
            "update_processor_config", {"processor_config": processor_config}
        )

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

            if backend_plugin_state.processor_config is not None:
                results = (
                    backend_plugin_state.processor_config._collect_validation_results(
                        backend_plugin_state.session_config
                    )
                    + backend_plugin_state.session_config._collect_validation_results()
                )

                not_handled = self.session_config_editor.handle_validation_results(results)

                not_handled = self.processor_config_editor.handle_validation_results(not_handled)

                not_handled = self.misc_error_view.handle_validation_results(not_handled)

                assert not_handled == []

    def on_app_model_update(self, app_model: AppModel) -> None:
        self.session_config_editor.setEnabled(app_model.plugin_state == PluginState.LOADED_IDLE)
        self.processor_config_editor.setEnabled(app_model.plugin_state == PluginState.LOADED_IDLE)

        self.start_button.setEnabled(
            app_model.is_ready_for_session() and app_model.backend_plugin_state.ready
        )

        self.stop_button.setEnabled(app_model.plugin_state == PluginState.LOADED_BUSY)

        if app_model.backend_plugin_state:
            self.session_config_editor.set_selected_sensor(
                app_model.backend_plugin_state.session_config.sensor_id,
                self.app_model.connected_sensors,
            )

    @classmethod
    def supports_multiple_subsweeps(self) -> bool:
        return False

    @classmethod
    @abc.abstractmethod
    def get_pidget_mapping(cls) -> PidgetFactoryMapping:
        pass

    @classmethod
    @abc.abstractmethod
    def get_processor_config_cls(cls) -> Type[ProcessorConfigT]:
        pass
