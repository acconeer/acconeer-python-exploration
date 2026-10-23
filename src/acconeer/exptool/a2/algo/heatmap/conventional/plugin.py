# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved

from __future__ import annotations

import logging
import platform
import typing as t
from pathlib import Path

import typing_extensions as te

from PySide6.QtWidgets import QPushButton, QVBoxLayout

import pyqtgraph as pg

from acconeer.exptool import a2
from acconeer.exptool.a2.algo._plugins import A2ViewPluginBase
from acconeer.exptool.a2.algo.heatmap._plot_pidget_mapping import get_plot_config_pidget_mapping
from acconeer.exptool.a2.algo.heatmap.backend_plugin_common import (
    BackendPlugin,
    SharedState,
)
from acconeer.exptool.a2.algo.heatmap.plot_config_common import HeatmapPlotConfig
from acconeer.exptool.app.new import (
    AppModel,
    Message,
    MiscErrorView,
    PluginGeneration,
    visual_policies,
)
from acconeer.exptool.app.new.ui import AttrsConfigEditor, GroupBox, icons
from acconeer.exptool.app.new.ui.components import GotoResourceTabButton
from acconeer.exptool.app.new.ui.components.a2 import SessionConfigEditor

from . import _pidget_mapping
from .config import HeatmapAndSessionConfig, HeatmapConfig, heatmap_config_timeline
from .processor import HeatmapProcessor


if platform.system() == "Windows":
    pg.setConfigOptions(useOpenGL=True)

log = logging.getLogger(__name__)

HEATMAP_CONFIG_DATASET_NAME = "plugin_config"

ALGO_GROUP_NAME = "conventional_heatmap"


def _create_config_editor() -> AttrsConfigEditor[HeatmapConfig]:
    return AttrsConfigEditor(
        title="Heatmap generation parameters",
        factory_mapping=_pidget_mapping.get_config_pidget_mapping(),
        config_type=HeatmapConfig,
        save_load_buttons=True,
    )


class ViewPlugin(A2ViewPluginBase):
    def __init__(self, app_model: AppModel) -> None:
        super().__init__(app_model)

        self.start_button = QPushButton(icons.PLAY(), "Start measurement")
        self.start_button.setShortcut("space")
        self.start_button.setToolTip("Starts the session.\n\nShortcut: Space")
        self.start_button.clicked.connect(self._send_start_request)

        self.stop_button = QPushButton(icons.STOP(), "Stop")
        self.stop_button.setShortcut("space")
        self.stop_button.setToolTip("Stops the session.\n\nShortcut: Space")
        self.stop_button.clicked.connect(self._send_stop_request)

        self.misc_error_view = MiscErrorView(self)
        self.session_config_editor = SessionConfigEditor(single_subsweep=True)
        self.session_config_editor.set_data(a2.SessionConfig.default())
        self.session_config_editor.sig_update.connect(self._update_session_config)

        self.plot_config_editor = AttrsConfigEditor(
            title="Heatmap display parameters",
            factory_mapping=get_plot_config_pidget_mapping(),
            config_type=HeatmapPlotConfig,
            save_load_buttons=False,
        )
        self.plot_config_editor.set_data(HeatmapPlotConfig.default())
        self.plot_config_editor.sig_update.connect(
            lambda plot_config: BackendPlugin.update_plot_config.rpc(
                self.app_model.put_task, plot_config=plot_config
            )
        )

        self.heatmap_config_editor = _create_config_editor()

        self.heatmap_config_editor.set_data(HeatmapConfig.default())
        self.heatmap_config_editor.sig_update.connect(
            lambda heatmap_config: BackendPlugin.update_heatmap_config.rpc(
                self.app_model.put_task, heatmap_config=heatmap_config
            )
        )

        button_group = GroupBox.grid("Controls")
        button_group.layout().addWidget(self.start_button, 0, 0)
        button_group.layout().addWidget(self.stop_button, 0, 1)
        button_group.layout().addWidget(self.invalid_config_note, 1, 0, 1, 2)

        sticky_layout = QVBoxLayout()
        sticky_layout.setContentsMargins(0, 0, 0, 0)
        sticky_layout.addWidget(button_group)
        self.sticky_widget.setLayout(sticky_layout)

        scrolly_layout = QVBoxLayout()
        scrolly_layout.setContentsMargins(0, 0, 0, 0)
        scrolly_layout.addWidget(self.misc_error_view)
        scrolly_layout.addWidget(self.heatmap_config_editor)
        scrolly_layout.addWidget(self.plot_config_editor)
        scrolly_layout.addWidget(self.session_config_editor)
        self.scrolly_widget.setLayout(scrolly_layout)

        goto_resource_button = GotoResourceTabButton()
        goto_resource_button.clicked.connect(
            lambda: app_model.sig_resource_tab_input_block_requested.emit(
                HeatmapAndSessionConfig(
                    session_config=self.session_config_editor.get_data(),
                    heatmap_config=self.heatmap_config_editor.get_data(),
                )
            )
        )
        scrolly_layout.insertWidget(0, goto_resource_button)

    def _update_session_config(self, session_config: a2.SessionConfig) -> None:
        BackendPlugin.update_session_config.rpc(
            self.app_model.put_task, session_config=session_config
        )

    def on_app_model_update(self, app_model: AppModel) -> None:
        self.session_config_editor.setEnabled(visual_policies.config_editor_enabled(app_model))
        self.stop_button.setEnabled(visual_policies.stop_button_enabled(app_model))
        self.heatmap_config_editor.setEnabled(visual_policies.config_editor_enabled(app_model))
        self.plot_config_editor.setEnabled(visual_policies.config_editor_enabled(app_model))

        no_gui_errors = (
            self.session_config_editor.is_ready
            and self.heatmap_config_editor.is_ready
            and self.plot_config_editor.is_ready
        )
        start_enabled = visual_policies.start_button_enabled(
            app_model, extra_condition=self._config_ready(no_gui_errors)
        )

        self.start_button.setEnabled(start_enabled)

    def on_backend_state_update(
        self, state: t.Optional[SharedState[HeatmapConfig, HeatmapPlotConfig]]
    ) -> None:
        if state is None:
            self.session_config_editor.set_data(None)
            self.heatmap_config_editor.set_data(None)
            self.plot_config_editor.set_data(None)
            self._update_config_validity([])
        else:
            assert isinstance(state.heatmap_config, HeatmapConfig)
            self.session_config_editor.set_data(state.session_config)
            self.heatmap_config_editor.set_data(state.heatmap_config)
            self.plot_config_editor.set_data(state.plot_config)

            validation_results = state._collect_validation_results()
            self._update_config_validity(validation_results)
            not_handled = self.session_config_editor.handle_validation_results(validation_results)
            not_handled = self.heatmap_config_editor.handle_validation_results(not_handled)
            _ = self.misc_error_view.handle_validation_results(not_handled)


def _create_backend_plugin(
    callback: t.Callable[[Message], None], generation: PluginGeneration, key: str
) -> BackendPlugin[HeatmapConfig, HeatmapPlotConfig]:
    return BackendPlugin(
        callback=callback,
        generation=generation,
        key=key,
        heatmap_config_dataset_name=HEATMAP_CONFIG_DATASET_NAME,
        algo_group_name=ALGO_GROUP_NAME,
        heatmap_config_class=HeatmapConfig,
        heatmap_config_timeline=heatmap_config_timeline,
        heatmap_processor_class=HeatmapProcessor,
        plot_config_class=HeatmapPlotConfig,
    )


def _replay_dialog_get_config(
    path: Path,
) -> tuple[te.Literal["default", "loaded"], HeatmapConfig, a2.SessionConfig]:
    with a2.open_record(path) as record:
        session_config = record.session_config
        try:
            algo_group = record.require_algo_group(ALGO_GROUP_NAME)
            json_str = algo_group[HEATMAP_CONFIG_DATASET_NAME][()].decode()
            return ("loaded", heatmap_config_timeline.migrate(json_str), session_config)
        except Exception:
            return ("default", HeatmapConfig.default(), session_config)
