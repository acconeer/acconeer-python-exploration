# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import abc
import logging
from typing import Any, Generic, Optional, Type

from PySide6.QtWidgets import QPushButton, QVBoxLayout

from acconeer.exptool import a121
from acconeer.exptool.a121.algo._base import ProcessorConfigT
from acconeer.exptool.a121.algo._plugins._a121 import A121ViewPluginBase
from acconeer.exptool.app.new import (
    AppModel,
    AttrsConfigEditor,
    GroupBox,
    MiscErrorView,
    PidgetFactoryMapping,
    icons,
    visual_policies,
)
from acconeer.exptool.app.new.ui.components.a121 import (
    SessionConfigEditor,
    SmartMetadataView,
    SmartPerfCalcView,
)

from .backend_plugin import ProcessorBackendPluginBase, ProcessorBackendPluginSharedState


log = logging.getLogger(__name__)


class ProcessorViewPluginBase(A121ViewPluginBase, Generic[ProcessorConfigT]):
    def __init__(self, app_model: AppModel) -> None:
        super().__init__(app_model=app_model)

        self.sticky_layout = QVBoxLayout()
        self.sticky_layout.setContentsMargins(0, 0, 0, 0)
        self.scrolly_layout = QVBoxLayout()
        self.scrolly_layout.setContentsMargins(0, 0, 0, 0)

        self.start_button = QPushButton(icons.PLAY(), "Start measurement")
        self.stop_button = QPushButton(icons.STOP(), "Stop")
        self.start_button.clicked.connect(self._send_start_request)
        self.stop_button.clicked.connect(self._send_stop_request)

        self.start_button.setShortcut("space")
        self.start_button.setToolTip("Starts the session.\n\nShortcut: Space")
        self.stop_button.setShortcut("space")
        self.stop_button.setToolTip("Stops the session.\n\nShortcut: Space")

        button_group = GroupBox.grid("Controls", parent=self.sticky_widget)
        button_group.layout().addWidget(self.start_button, 0, 0)
        button_group.layout().addWidget(self.stop_button, 0, 1)
        self.sticky_layout.addWidget(button_group)

        self.metadata_view = SmartMetadataView(parent=self.scrolly_widget)
        self.scrolly_layout.addWidget(self.metadata_view)

        self.perf_calc_view = SmartPerfCalcView(parent=self.scrolly_widget)
        self.scrolly_layout.addWidget(self.perf_calc_view)

        self.processor_config_editor = AttrsConfigEditor(
            title="Processor parameters",
            factory_mapping=self.get_pidget_mapping(),
            config_type=self.get_processor_config_cls(),
            parent=self.scrolly_widget,
        )
        self.processor_config_editor.sig_update.connect(self._on_processor_config_update)
        self.scrolly_layout.addWidget(self.processor_config_editor)

        self.misc_error_view = MiscErrorView(self.scrolly_widget)
        self.scrolly_layout.addWidget(self.misc_error_view)

        self.session_config_editor = SessionConfigEditor(
            self.supports_multiple_subsweeps(),
            self.supports_multiple_sensors(),
            self.scrolly_widget,
        )
        self.session_config_editor.sig_update.connect(self._on_session_config_update)
        self.scrolly_layout.addWidget(self.session_config_editor)

        self.sticky_widget.setLayout(self.sticky_layout)
        self.scrolly_widget.setLayout(self.scrolly_layout)

    def _on_session_config_update(self, session_config: a121.SessionConfig) -> None:
        ProcessorBackendPluginBase.update_session_config.rpc(
            self.app_model.put_task, session_config=session_config
        )

    def _on_processor_config_update(self, processor_config: ProcessorConfigT) -> None:
        ProcessorBackendPluginBase[ProcessorConfigT, Any].update_processor_config.rpc(
            self.app_model.put_task,
            processor_config=processor_config,
        )

    def on_backend_state_update(
        self,
        backend_plugin_state: Optional[ProcessorBackendPluginSharedState[ProcessorConfigT]],
    ) -> None:
        if backend_plugin_state is None:
            self.session_config_editor.set_data(None)
            self.processor_config_editor.set_data(None)
            self.metadata_view.set_data(None)
            self.perf_calc_view.set_data()
        else:
            assert isinstance(backend_plugin_state, ProcessorBackendPluginSharedState)
            assert isinstance(
                backend_plugin_state.processor_config, self.get_processor_config_cls()
            )

            self.session_config_editor.set_data(backend_plugin_state.session_config)
            self.processor_config_editor.set_data(backend_plugin_state.processor_config)
            self.metadata_view.set_data(backend_plugin_state.metadata)
            self.perf_calc_view.set_data(
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
        gui_no_errors = (
            self.session_config_editor.is_ready and self.processor_config_editor.is_ready
        )

        visual_policies.apply_enabled_policy(
            visual_policies.config_editor_enabled,
            app_model,
            widgets=[self.session_config_editor, self.processor_config_editor],
        )

        self.stop_button.setEnabled(visual_policies.stop_button_enabled(app_model))
        self.start_button.setEnabled(
            visual_policies.start_button_enabled(app_model, extra_condition=gui_no_errors)
        )

        self.session_config_editor.set_selectable_sensors(self.app_model.connected_sensors)

    @classmethod
    def supports_multiple_subsweeps(self) -> bool:
        return False

    @classmethod
    def supports_multiple_sensors(self) -> bool:
        return False

    @classmethod
    @abc.abstractmethod
    def get_pidget_mapping(cls) -> PidgetFactoryMapping:
        pass

    @classmethod
    @abc.abstractmethod
    def get_processor_config_cls(cls) -> Type[ProcessorConfigT]:
        pass
