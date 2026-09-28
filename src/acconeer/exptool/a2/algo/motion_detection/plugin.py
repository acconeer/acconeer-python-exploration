# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import copy
import logging
import os
import platform
import typing as t
from collections import deque
from pathlib import Path

import attrs
import h5py
import numpy as np
import numpy.typing as npt

from PySide6.QtCore import QSize
from PySide6.QtGui import QFont, QTransform
from PySide6.QtWidgets import QPushButton, QSizePolicy, QVBoxLayout

import pyqtgraph as pg
import pyqtgraph.opengl as gl

import acconeer.exptool as et
import acconeer.exptool.a2.algo._utils as algo_utils
from acconeer.exptool import a2
from acconeer.exptool._core.entities.validation_result import ValidationResult
from acconeer.exptool.a2._core.entities import Metadata
from acconeer.exptool.a2.algo._detection_geometry import (
    DetectionVolume,
    SensorInstallation,
    load_detection_geometry,
    save_detection_geometry,
)
from acconeer.exptool.a2.algo._plugin_specs.motion_detection import PluginPresetId
from acconeer.exptool.a2.algo._plugins import A2BackendPluginBase, A2ViewPluginBase
from acconeer.exptool.a2.algo._shared_config import (
    room_z_bounds_m,
    session_abstraction_config_timeline,
)
from acconeer.exptool.a2.algo._shared_pidget_mapping import (
    get_detection_volume_pidget_mapping,
    get_sensor_installation_pidget_mapping,
    get_session_abstraction_pidget_mapping,
)
from acconeer.exptool.a2.algo.heatmap.backend_plugin_common import (
    HeatmapPlotOrientation,
    TabState,
)
from acconeer.exptool.a2.algo.heatmap.cartesian_plot import CartesianHeatmapPlotWithGrid
from acconeer.exptool.a2.algo.heatmap.gl_sensor_model import GLSensorModel
from acconeer.exptool.a2.algo.heatmap.gl_view_widget import GuardedGLViewWidget
from acconeer.exptool.a2.algo.noise_normalization import (
    NoiseNormalizationRecording,
    load_noise_normalization_recording,
    save_noise_normalization_recording,
)
from acconeer.exptool.app.new import (
    AppModel,
    GeneralMessage,
    HandledException,
    MiscErrorView,
    PlotPluginBase,
    backend,
    is_task,
    visual_policies,
)
from acconeer.exptool.app.new.ui import AttrsConfigEditor, DataEditor, GroupBox, icons
from acconeer.exptool.app.new.ui.components import TabPGWidget
from acconeer.exptool.app.new.ui.components.a2 import SessionConfigEditor
from acconeer.exptool.type_migration import MigrationError

from . import _pidget_mapping
from .config import (
    HeatmapDisplayMode,
    MotionDetectionConfig,
    PlotSettings,
    WallMountSessionAbstractionConfig,
    get_sitting_detection_configs,
    get_walking_detection_configs,
)
from .motion_detection_processor import MotionDetectionProcessor, MotionDetectionResult


if platform.system() == "Windows":
    pg.setConfigOptions(useOpenGL=True)

log = logging.getLogger(__name__)

PROCESSOR_CONFIG_DATASET_NAME = "processor_config"
SESSION_ABSTRACTION_CONFIG_DATASET_NAME = "session_abstraction_config"
PLOT_SETTINGS_DATASET_NAME = "plot_settings"
ALGO_GROUP_NAME = "motion_detection"

DEGREE_SYMBOL = "°"

SKIN = os.environ.get("ACC_SKIN", "none").lower()
TEXT_COLOR = "white" if SKIN == "tron" else "black"
BACKGROUND_COLOR = "black" if SKIN == "tron" else "white"

_ICON_SIZE = QSize(25, 25)
_BUTTON_SIZE = QSize(30, 30)

_PEAK_BRUSH = pg.mkBrush(255, 50, 50, 220)
_PEAK_SIZE = 10

_BELOW_THRESH_SENTINEL = -1.0  # dB; always below any above-threshold cell (≥ 0 dB)

_BOUNDS_PEN = pg.mkPen(color=(0, 100, 220), width=2)


def _make_masked_viridis_lut() -> npt.NDArray[np.uint8]:
    lut = et.utils.pg_mpl_cmap("viridis").copy()
    lut[0] = [128, 128, 128, 180]  # semi-transparent grey for below-threshold cells
    return lut  # type: ignore[no-any-return]


def _make_viridis_lut() -> npt.NDArray[np.uint8]:
    return et.utils.pg_mpl_cmap("viridis").copy()  # type: ignore[no-any-return]


@attrs.mutable
class SharedState:
    session_config: a2.SessionConfig
    session_abstraction_config: WallMountSessionAbstractionConfig
    processor_config: MotionDetectionConfig
    sensor_installation: SensorInstallation
    detection_volume: DetectionVolume
    metadata: Metadata | None
    noise_normalization_recording: NoiseNormalizationRecording | None
    heatmap_plot_orientation: HeatmapPlotOrientation
    tab_state: TabState
    replaying_record: bool
    plot_settings: PlotSettings

    def _collect_validation_results(self) -> list[ValidationResult]:
        return [
            *self.session_abstraction_config._collect_validation_results(
                self.sensor_installation, self.detection_volume
            ),
            *self.processor_config._collect_validation_results(
                self.session_config, self.sensor_installation, self.detection_volume
            ),
            *self.session_config._collect_validation_results(),
            *self.sensor_installation._collect_validation_results(),
            *self.detection_volume._collect_validation_results(),
        ]


class BackendPlugin(A2BackendPluginBase[SharedState]):
    def __init__(self, *args: t.Any, **kwargs: t.Any) -> None:
        super().__init__(*args, **kwargs)
        processor_config, session_abstraction_config, sensor_installation, detection_volume = (
            get_walking_detection_configs()
        )
        session_config = session_abstraction_config.get_session_config(
            sensor_installation, detection_volume
        )
        self.shared_state = SharedState(
            session_config=session_config,
            session_abstraction_config=session_abstraction_config,
            processor_config=processor_config,
            sensor_installation=sensor_installation,
            detection_volume=detection_volume,
            metadata=None,
            noise_normalization_recording=None,
            heatmap_plot_orientation=HeatmapPlotOrientation(),
            tab_state=TabState.ANGULAR,
            replaying_record=False,
            plot_settings=PlotSettings(),
        )
        self.processor: MotionDetectionProcessor | None = None
        self.broadcast()

    def _start_session(self, recorder: a2.H5Recorder | None) -> None:
        assert self.client is not None

        if (
            self.shared_state.noise_normalization_recording is None
            or self.shared_state.session_config
            != self.shared_state.noise_normalization_recording.noise_config
        ) and not self.shared_state.replaying_record:
            try:
                self.shared_state.noise_normalization_recording = (
                    NoiseNormalizationRecording.create(
                        self.client, self.shared_state.session_config
                    )
                )
            except Exception as exc:
                msg = "Failed to record noise for normalization"
                raise HandledException(msg) from exc

        self.shared_state.replaying_record = False

        if recorder:
            self.client.attach_recorder(recorder)
            algo_group = recorder.require_algo_group(ALGO_GROUP_NAME)
            algo_group.create_dataset(
                PROCESSOR_CONFIG_DATASET_NAME,
                data=self.shared_state.processor_config.to_json(),
            )
            algo_group.create_dataset(
                SESSION_ABSTRACTION_CONFIG_DATASET_NAME,
                data=self.shared_state.session_abstraction_config.to_json(),
            )
            save_detection_geometry(
                algo_group,
                self.shared_state.sensor_installation,
                self.shared_state.detection_volume,
            )
            save_noise_normalization_recording(
                algo_group, self.shared_state.noise_normalization_recording
            )

        self.shared_state.metadata = self.client.setup_session(self.shared_state.session_config)

        self.processor = MotionDetectionProcessor(
            self.shared_state.session_config,
            self.shared_state.processor_config,
            self.shared_state.sensor_installation,
            self.shared_state.detection_volume,
            self.shared_state.noise_normalization_recording,
        )

        self.client.start_session()
        self.broadcast()

    def get_next(self) -> None:
        assert self.client is not None

        result = self.client.get_next(format=a2.Client.ResultFormat.SOLE)

        if self.processor is None:
            self.callback(backend.PlotMessage(result=None))
        else:
            proc_result = self.processor.process(result)
            self.callback(backend.PlotMessage(result=proc_result))

    def end_session(self) -> None:
        assert self.client is not None

        self.client.stop_session()

        recorder = self.client.detach_recorder()
        if recorder is not None:
            recorder.close()

        self.processor = None

    @is_task
    def update_processor_config(self, processor_config: MotionDetectionConfig) -> None:
        self.shared_state.processor_config = processor_config
        self.broadcast()

    @is_task
    def update_session_abstraction_config(
        self, session_abstraction_config: WallMountSessionAbstractionConfig
    ) -> None:
        self.shared_state.session_abstraction_config = session_abstraction_config
        self._update_session_config()
        self.broadcast()

    @is_task
    def update_sensor_installation(self, sensor_installation: SensorInstallation) -> None:
        self.shared_state.sensor_installation = sensor_installation
        self._update_session_config()
        self.broadcast()

    @is_task
    def update_detection_volume(self, detection_volume: DetectionVolume) -> None:
        self.shared_state.detection_volume = detection_volume
        self._update_session_config()
        self.broadcast()

    def _update_session_config(self) -> None:
        """Derive the session config from the session abstraction and the
        geometry, keeping the current one where that fails (validation
        reports why)."""
        self.shared_state.session_config = (
            self.shared_state.session_abstraction_config.try_get_session_config(
                self.shared_state.sensor_installation, self.shared_state.detection_volume
            )
            or self.shared_state.session_config
        )

    @is_task
    def update_tab_display(self, tab: TabState) -> None:
        self.shared_state.tab_state = tab
        self.broadcast()

    @is_task
    def heatmap_plot_rotate(self) -> None:
        self.shared_state.heatmap_plot_orientation.rotation += 90
        self.shared_state.heatmap_plot_orientation.rotation %= 360
        self.broadcast()

    @is_task
    def heatmap_plot_invert_x(self) -> None:
        self.shared_state.heatmap_plot_orientation.inv_x = (
            not self.shared_state.heatmap_plot_orientation.inv_x
        )
        self.broadcast()

    @is_task
    def heatmap_plot_invert_y(self) -> None:
        self.shared_state.heatmap_plot_orientation.inv_y = (
            not self.shared_state.heatmap_plot_orientation.inv_y
        )
        self.broadcast()

    @is_task
    def heatmap_plot_reset(self) -> None:
        self.shared_state.heatmap_plot_orientation = HeatmapPlotOrientation()
        self.broadcast()

    @is_task
    def update_plot_settings(self, plot_settings: PlotSettings) -> None:
        self.shared_state.plot_settings = plot_settings
        self.broadcast()

    @is_task
    def set_preset(self, preset_id: int) -> None:
        if preset_id == PluginPresetId.WALKING.value:
            processor_config, session_abstraction_config, sensor_installation, detection_volume = (
                get_walking_detection_configs()
            )
        elif preset_id == PluginPresetId.SITTING.value:
            processor_config, session_abstraction_config, sensor_installation, detection_volume = (
                get_sitting_detection_configs()
            )
        else:
            msg = f"Unknown preset id {preset_id}"
            raise RuntimeError(msg)
        self.shared_state.processor_config = processor_config
        self.shared_state.session_abstraction_config = session_abstraction_config
        self.shared_state.sensor_installation = sensor_installation
        self.shared_state.detection_volume = detection_volume
        self.shared_state.session_config = session_abstraction_config.get_session_config(
            sensor_installation, detection_volume
        )
        self.broadcast()

    def load_from_record_setup(
        self,
        *,
        record: a2.H5Record,
        config_override: t.Any | None = None,
        context_override: t.Any | None = None,
    ) -> None:
        if context_override is not None:
            self._logger.warning(f"Ignoring context override of type: {type(context_override)}")

        _, default_session_abstraction_config, default_installation, default_volume = (
            get_walking_detection_configs()
        )
        self.update_session_abstraction_config(default_session_abstraction_config)
        self.shared_state.sensor_installation = default_installation
        self.shared_state.detection_volume = default_volume

        try:
            algo_group = record.require_algo_group(ALGO_GROUP_NAME)
        except KeyError as exc:
            msg = "Cannot replay: recording was not created by this plugin."
            raise HandledException(msg) from exc

        noise_normalization_recording = load_noise_normalization_recording(algo_group)
        if noise_normalization_recording is None:
            msg = "Cannot replay: no noise normalization recording found in file."
            raise HandledException(msg)

        self.shared_state.replaying_record = True
        self.shared_state.noise_normalization_recording = noise_normalization_recording

        if config_override is None:
            try:
                dataset = algo_group.get(PROCESSOR_CONFIG_DATASET_NAME)
                if dataset is not None:
                    processor_config = MotionDetectionConfig.from_json(dataset[()].decode())
                else:
                    processor_config = self.shared_state.processor_config
            except Exception:
                msg = "Could not load processor config, falling back to default"
                self.callback(backend.StatusMessage(status=msg))
                processor_config = self.shared_state.processor_config
        elif isinstance(config_override, ReplayDialogConfig):
            # The override's geometry is the recorded one (loaded below) and
            # only serves to validate the processor config in the dialog.
            processor_config = config_override.processor_config
        else:
            msg = f"'config_override' was of incorrect type {type(config_override)}"
            raise TypeError(msg)

        self.update_processor_config(processor_config)

        # The geometry loads first: migrating an old session abstraction
        # config needs the sensor installation.
        try:
            geometry = load_detection_geometry(algo_group)
            if geometry is not None:
                self.shared_state.sensor_installation, self.shared_state.detection_volume = (
                    geometry
                )
                self._update_session_config()
        except Exception:
            msg = "Could not load sensor installation or detection volume."
            self.callback(backend.StatusMessage(status=msg))

        try:
            dataset = algo_group.get(SESSION_ABSTRACTION_CONFIG_DATASET_NAME)
            if dataset is not None:
                sac = session_abstraction_config_timeline.migrate(
                    dataset[()].decode(),
                    completer=lambda _: self.shared_state.sensor_installation,
                )
                self.update_session_abstraction_config(sac)
        except Exception:
            msg = "Could not load sensor setup config."
            self.callback(backend.StatusMessage(status=msg))

        try:
            self.shared_state.session_config = record.session_config
        except Exception:
            msg = "Could not load session config."
            self.callback(backend.StatusMessage(status=msg))

        self.broadcast()

    def _load_from_cache(self, file: h5py.File) -> SharedState:
        cached: dict[str, t.Any] = {}
        if dataset := file.get(PROCESSOR_CONFIG_DATASET_NAME):
            cached["processor_config"] = MotionDetectionConfig.from_json(dataset[()].decode())

        if geometry := load_detection_geometry(file):
            cached["sensor_installation"], cached["detection_volume"] = geometry

        if dataset := file.get(SESSION_ABSTRACTION_CONFIG_DATASET_NAME):
            sensor_installation = cached.get(
                "sensor_installation", self.shared_state.sensor_installation
            )
            cached["session_abstraction_config"] = session_abstraction_config_timeline.migrate(
                dataset[()].decode(), completer=lambda _: sensor_installation
            )

        if noise_group := file.get("noise_group"):
            try:
                cached["noise_normalization_recording"] = load_noise_normalization_recording(
                    noise_group
                )
            except MigrationError:
                self._logger.warning("Could not load noise normalization recording from cache")

        if dataset := file.get("heatmap_plot_orientation"):
            cached["heatmap_plot_orientation"] = HeatmapPlotOrientation.from_json(
                dataset[()].decode()
            )

        if dataset := file.get(PLOT_SETTINGS_DATASET_NAME):
            cached["plot_settings"] = PlotSettings.from_json(dataset[()].decode())

        state = attrs.evolve(self.shared_state, **cached)
        state.session_config = (
            state.session_abstraction_config.try_get_session_config(
                state.sensor_installation, state.detection_volume
            )
            or state.session_config
        )
        return state

    def save_to_cache(self, file: h5py.File) -> None:
        file.create_dataset(
            PROCESSOR_CONFIG_DATASET_NAME,
            data=self.shared_state.processor_config.to_json(),
        )
        file.create_dataset(
            SESSION_ABSTRACTION_CONFIG_DATASET_NAME,
            data=self.shared_state.session_abstraction_config.to_json(),
        )
        save_detection_geometry(
            file, self.shared_state.sensor_installation, self.shared_state.detection_volume
        )
        noise_group = file.create_group("noise_group")
        save_noise_normalization_recording(
            noise_group, self.shared_state.noise_normalization_recording
        )
        file.create_dataset(
            "heatmap_plot_orientation",
            data=self.shared_state.heatmap_plot_orientation.to_json(),
        )
        file.create_dataset(
            PLOT_SETTINGS_DATASET_NAME,
            data=self.shared_state.plot_settings.to_json(),
        )


def _create_processor_config_editor() -> AttrsConfigEditor[MotionDetectionConfig]:
    return AttrsConfigEditor(
        title="Motion Detection",
        factory_mapping=_pidget_mapping.get_motion_detection_config_pidget_mapping(),
        config_type=MotionDetectionConfig,
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

        default_processor_config, default_sac, default_installation, default_volume = (
            get_walking_detection_configs()
        )
        default_session_config = default_sac.get_session_config(
            default_installation, default_volume
        )

        self.sensor_installation_editor = AttrsConfigEditor(
            title="Sensor Installation",
            factory_mapping=get_sensor_installation_pidget_mapping(),
            config_type=SensorInstallation,
            save_load_buttons=True,
        )
        self.sensor_installation_editor.set_data(default_installation)
        self.sensor_installation_editor.sig_update.connect(self._on_sensor_installation_update)

        self.detection_volume_editor = AttrsConfigEditor(
            title="Detection Volume",
            factory_mapping=get_detection_volume_pidget_mapping(),
            config_type=DetectionVolume,
            save_load_buttons=True,
        )
        self.detection_volume_editor.set_data(default_volume)
        self.detection_volume_editor.sig_update.connect(self._on_detection_volume_update)

        self.processor_config_editor = _create_processor_config_editor()
        self.processor_config_editor.set_data(default_processor_config)
        self.processor_config_editor.sig_update.connect(self._on_processor_config_update)

        self.session_abstraction_editor = AttrsConfigEditor(
            title="Sensor Setup",
            factory_mapping=get_session_abstraction_pidget_mapping(),
            config_type=WallMountSessionAbstractionConfig,
            save_load_buttons=True,
        )
        self.session_abstraction_editor.set_data(default_sac)
        self.session_abstraction_editor.sig_update.connect(
            lambda sac: BackendPlugin.update_session_abstraction_config.rpc(
                self.app_model.put_task, session_abstraction_config=sac
            )
        )

        self.plot_settings_editor = AttrsConfigEditor(
            title="Plot Settings",
            factory_mapping=_pidget_mapping.get_plot_settings_pidget_mapping(),
            config_type=PlotSettings,
            save_load_buttons=False,
        )
        self.plot_settings_editor.set_data(PlotSettings())
        self.plot_settings_editor.sig_update.connect(
            lambda ps: BackendPlugin.update_plot_settings.rpc(
                self.app_model.put_task, plot_settings=ps
            )
        )

        self.session_config_editor = SessionConfigEditor(single_subsweep=False)
        self.session_config_editor.set_data(default_session_config)
        self.session_config_editor.setEnabled(False)

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
        scrolly_layout.addWidget(self.sensor_installation_editor)
        scrolly_layout.addWidget(self.detection_volume_editor)
        scrolly_layout.addWidget(self.processor_config_editor)
        scrolly_layout.addWidget(self.session_abstraction_editor)
        scrolly_layout.addWidget(self.plot_settings_editor)
        scrolly_layout.addWidget(self.session_config_editor)
        self.scrolly_widget.setLayout(scrolly_layout)

    def on_app_model_update(self, app_model: AppModel) -> None:
        self.stop_button.setEnabled(visual_policies.stop_button_enabled(app_model))

        editors_enabled = visual_policies.config_editor_enabled(app_model)
        self.processor_config_editor.setEnabled(editors_enabled)
        self.session_abstraction_editor.setEnabled(editors_enabled)
        self.sensor_installation_editor.setEnabled(editors_enabled)
        self.detection_volume_editor.setEnabled(editors_enabled)

        no_gui_errors = (
            self.processor_config_editor.is_ready
            and self.session_abstraction_editor.is_ready
            and self.sensor_installation_editor.is_ready
            and self.detection_volume_editor.is_ready
        )
        start_enabled = visual_policies.start_button_enabled(
            app_model, extra_condition=self._config_ready(no_gui_errors)
        )
        self.start_button.setEnabled(start_enabled)

    def on_backend_state_update(self, state: SharedState | None) -> None:
        if state is None:
            self.processor_config_editor.set_data(None)
            self.session_abstraction_editor.set_data(None)
            self.sensor_installation_editor.set_data(None)
            self.detection_volume_editor.set_data(None)
            self.plot_settings_editor.set_data(None)
            self.session_config_editor.set_data(None)
            self._update_config_validity([])
        else:
            self.processor_config_editor.set_data(state.processor_config)
            self.session_abstraction_editor.set_data(state.session_abstraction_config)
            self.sensor_installation_editor.set_data(state.sensor_installation)
            self.detection_volume_editor.set_data(state.detection_volume)
            self.plot_settings_editor.set_data(state.plot_settings)
            self.session_config_editor.set_data(state.session_config)
            self.session_config_editor.setEnabled(False)

            validation_results = state._collect_validation_results()
            self._update_config_validity(validation_results)
            not_handled = self.session_abstraction_editor.handle_validation_results(
                validation_results
            )
            not_handled = self.processor_config_editor.handle_validation_results(not_handled)
            not_handled = self.sensor_installation_editor.handle_validation_results(not_handled)
            not_handled = self.detection_volume_editor.handle_validation_results(not_handled)
            _ = self.misc_error_view.handle_validation_results(not_handled)

    def _on_processor_config_update(self, config: MotionDetectionConfig) -> None:
        self.processor_config_editor.set_data(config)
        BackendPlugin.update_processor_config.rpc(self.app_model.put_task, processor_config=config)

    def _on_sensor_installation_update(self, sensor_installation: SensorInstallation) -> None:
        self.sensor_installation_editor.set_data(sensor_installation)
        BackendPlugin.update_sensor_installation.rpc(
            self.app_model.put_task, sensor_installation=sensor_installation
        )

    def _on_detection_volume_update(self, detection_volume: DetectionVolume) -> None:
        self.detection_volume_editor.set_data(detection_volume)
        BackendPlugin.update_detection_volume.rpc(
            self.app_model.put_task, detection_volume=detection_volume
        )


class PlotPlugin(PlotPluginBase):
    INTERIM_AZ_START = -65
    INTERIM_AZ_SPAN = 130
    INTERIM_EL_START = -45
    INTERIM_EL_SPAN = 90

    def __init__(self, app_model: AppModel) -> None:
        super().__init__(app_model)
        self._plot_job: MotionDetectionResult | None = None
        self._session_config: a2.SessionConfig | None = None
        self._processor_config: MotionDetectionConfig | None = None
        self._sensor_installation: SensorInstallation | None = None
        self._detection_volume: DetectionVolume | None = None
        self.heatmap_plot_orientation: HeatmapPlotOrientation = HeatmapPlotOrientation()

        # --- Plot orientation controls ---
        self._rotate_button = QPushButton()
        self._rotate_button.setToolTip("Rotate plot counterclockwise")
        self._rotate_button.setIcon(icons.ROTATE())
        self._rotate_button.setFixedSize(_BUTTON_SIZE)
        self._rotate_button.setIconSize(_ICON_SIZE)
        self._rotate_button.clicked.connect(
            lambda: BackendPlugin.heatmap_plot_rotate.rpc(app_model.put_task)
        )

        self._inv_x_button = QPushButton()
        self._inv_x_button.setToolTip("Mirror x-axis")
        self._inv_x_button.setIcon(icons.MIRROR())
        self._inv_x_button.setFixedSize(_BUTTON_SIZE)
        self._inv_x_button.setIconSize(_ICON_SIZE)
        self._inv_x_button.setFlat(True)
        self._inv_x_button.setCheckable(True)
        self._inv_x_button.clicked.connect(
            lambda: BackendPlugin.heatmap_plot_invert_x.rpc(app_model.put_task)
        )

        self._inv_y_button = QPushButton()
        self._inv_y_button.setToolTip("Mirror y-axis")
        self._inv_y_button.setIcon(icons.MIRROR_90())
        self._inv_y_button.setFixedSize(_BUTTON_SIZE)
        self._inv_y_button.setIconSize(_ICON_SIZE)
        self._inv_y_button.setFlat(True)
        self._inv_y_button.setCheckable(True)
        self._inv_y_button.clicked.connect(
            lambda: BackendPlugin.heatmap_plot_invert_y.rpc(app_model.put_task)
        )

        reset_orientation_button = QPushButton()
        reset_orientation_button.setToolTip("Reset plot orientation")
        reset_orientation_button.setIcon(icons.RESTORE(color=icons.TEXT_GREY))
        reset_orientation_button.setFixedSize(_BUTTON_SIZE)
        reset_orientation_button.setIconSize(_ICON_SIZE)
        reset_orientation_button.clicked.connect(
            lambda: BackendPlugin.heatmap_plot_reset.rpc(app_model.put_task)
        )

        plot_button_group_box = GroupBox.horizontal("Plot orientation")
        plot_button_group_box.setMaximumWidth(200)
        plot_button_group_box.layout().addWidget(self._rotate_button)
        plot_button_group_box.layout().addWidget(self._inv_x_button)
        plot_button_group_box.layout().addWidget(self._inv_y_button)
        plot_button_group_box.layout().addWidget(reset_orientation_button)

        self.tab_widget = TabPGWidget(right_controls=plot_button_group_box)

        _masked_lut = _make_masked_viridis_lut()

        # --- 2D Cartesian Heatmap tab ---
        self.cart_heatmap_plot = CartesianHeatmapPlotWithGrid()
        self.cart_heatmap_plot.setLookupTable(_masked_lut)
        self.cart_heatmap_layout = pg.GraphicsLayoutWidget()
        self.cart_heatmap_plot_item = self.cart_heatmap_layout.addPlot(row=0, col=0)
        self.cart_heatmap_plot_item.setAspectLocked(True, ratio=1)
        self.cart_heatmap_colorbar = self.cart_heatmap_plot_item.addColorBar(
            self.cart_heatmap_plot, colorMap="viridis", interactive=False
        )
        self.cart_heatmap_colorbar.vb.setMouseEnabled(x=False, y=False)
        self.cart_heatmap_colorbar.vb.mouseDragEvent = lambda ev: None
        self.cart_heatmap_colorbar.vb.mouseClickEvent = lambda ev: None
        self.cart_heatmap_colorbar.vb.wheelEvent = lambda ev: None
        _colorbar_font = QFont()
        _colorbar_font.setPixelSize(10)
        self.cart_heatmap_colorbar.axis.setStyle(tickFont=_colorbar_font)
        self.cart_heatmap_plot_item.addItem(self.cart_heatmap_plot)

        # Peak scatter overlay on Cartesian tab
        self._cart_peak_scatter = pg.ScatterPlotItem(
            pen=None, brush=_PEAK_BRUSH, size=_PEAK_SIZE, symbol="o"
        )
        self._cart_peak_scatter.setZValue(10)
        self.cart_heatmap_plot_item.addItem(self._cart_peak_scatter)

        # --- 3D view tab ---
        self.sensor_model = GLSensorModel()
        self.sensor_text_item = gl.GLTextItem(
            pos=np.zeros((3,)),
            color=TEXT_COLOR,
            text="Sensor",
            font=QFont("Helvetica", 7),
        )
        self.heatmap_gl_widget = GuardedGLViewWidget()
        self.heatmap_gl_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.heatmap_gl_widget.setBackgroundColor(BACKGROUND_COLOR)
        for item in self.sensor_model.items:
            self.heatmap_gl_widget.addItem(item)
        self.axis_item = gl.GLAxisItem()
        self.axis_item.setSize(1, 1, 1)

        self.x_axis_text_item = gl.GLTextItem(
            pos=np.array([1, 0, 0]), text="+x", font=QFont("Helvetica", 7), color=TEXT_COLOR
        )
        self.y_axis_text_item = gl.GLTextItem(
            pos=np.array([0, 1, 0]), text="+y", font=QFont("Helvetica", 7), color=TEXT_COLOR
        )
        self.z_axis_text_item = gl.GLTextItem(
            pos=np.array([0, 0, 1]), text="+z", font=QFont("Helvetica", 7), color=TEXT_COLOR
        )
        self.heatmap_gl_widget.addItem(self.axis_item)
        self.heatmap_gl_widget.addItem(self.x_axis_text_item)
        self.heatmap_gl_widget.addItem(self.y_axis_text_item)
        self.heatmap_gl_widget.addItem(self.z_axis_text_item)

        _setup_spherical_coordinates(
            self.heatmap_gl_widget,
            self.INTERIM_AZ_START,
            self.INTERIM_AZ_SPAN,
            self.INTERIM_EL_START,
            self.INTERIM_EL_SPAN,
            min_range=0.5,
            max_range=1.0,
        )

        # Peak scatter overlay on 3D tab
        self._gl_peak_scatter = gl.GLScatterPlotItem(size=8, color=(1.0, 0.2, 0.2, 1.0))
        self._gl_peak_scatter.setGLOptions("translucent")
        self.heatmap_gl_widget.addItem(self._gl_peak_scatter)

        # --- Add tabs ---
        # Added first so it is the tab shown by default (TabPGWidget shows tab id 0).
        CARTESIAN_TAB_ID = 1
        self.tab_widget.newTab(
            self.heatmap_gl_widget,
            "3D view",
            lambda: BackendPlugin.update_tab_display.rpc(app_model.put_task, tab=TabState.ANGULAR),
        )
        self.tab_widget.newTab(
            self.cart_heatmap_layout,
            "2D Heatmap",
            lambda: BackendPlugin.update_tab_display.rpc(
                app_model.put_task, tab=TabState.HEATMAP_CARTESIAN
            ),
        )

        self.tab_widget._button_group.idToggled.connect(
            lambda button_id, checked: plot_button_group_box.setEnabled(
                button_id == CARTESIAN_TAB_ID and checked
            )
        )

        layout = QVBoxLayout()
        layout.addWidget(self.tab_widget)
        self.setLayout(layout)

        self.heatmap_2d_plot_smooth_max = et.utils.SmoothMax(10.0, tau_decay=0.1, tau_grow=0.1)

        self._peak_history: deque[list[t.Any]] = deque(maxlen=1)
        self._history_num_samples: int = 1
        self._history_duration_s: float = PlotSettings().history_duration_s
        self._heatmap_display_mode: HeatmapDisplayMode | None = None
        self._masked_viridis_lut = _masked_lut
        self._standard_viridis_lut = _make_viridis_lut()
        self._cart_bounds_item = pg.PlotCurveItem(pen=_BOUNDS_PEN)

    def on_backend_state_update(self, state: SharedState | None) -> None:
        if state is None:
            return

        frame_rate = algo_utils.get_effective_frame_rate(state.session_config)
        # The processor rejects a session config without a rate at session start.
        assert frame_rate is not None

        self._history_duration_s = state.plot_settings.history_duration_s
        new_num_samples = max(1, round(self._history_duration_s * frame_rate))
        if new_num_samples != self._history_num_samples:
            self._history_num_samples = new_num_samples
            self._peak_history = deque(
                list(self._peak_history)[-new_num_samples:],
                maxlen=new_num_samples,
            )

        new_display_mode = state.plot_settings.heatmap_display_mode
        if new_display_mode != self._heatmap_display_mode:
            self._heatmap_display_mode = new_display_mode
            lut = (
                self._masked_viridis_lut
                if new_display_mode == HeatmapDisplayMode.HEATMAP_MASKED
                else self._standard_viridis_lut
            )
            self.cart_heatmap_plot.setLookupTable(lut)
            heatmap_off = new_display_mode == HeatmapDisplayMode.HEATMAP_OFF
            if heatmap_off:
                self.cart_heatmap_plot.clearData()
            self.cart_heatmap_colorbar.setVisible(not heatmap_off)

        config_changed = (
            self._session_config != state.session_config
            or self._processor_config != state.processor_config
            or self._sensor_installation != state.sensor_installation
            or self._detection_volume != state.detection_volume
        )
        if config_changed:
            self._session_config = state.session_config
            self._processor_config = state.processor_config
            self._sensor_installation = state.sensor_installation
            self._detection_volume = state.detection_volume

            az_angles = state.processor_config.az_angles(state.detection_volume).tolist()
            az_angle_range = state.processor_config.effective_az_angle_range(
                state.detection_volume
            )
            self.cart_heatmap_plot.update_grid(state.session_config, az_angles, az_angle_range)
            self.cart_heatmap_plot_item.autoRange()

            self.heatmap_2d_plot_smooth_max = et.utils.SmoothMax(
                frame_rate, tau_decay=0.1, tau_grow=0.1
            )

        orientation_changed = self.heatmap_plot_orientation != state.heatmap_plot_orientation
        if orientation_changed or config_changed:
            self.heatmap_plot_orientation = state.heatmap_plot_orientation
            self._inv_x_button.setChecked(self.heatmap_plot_orientation.inv_x)
            self._inv_y_button.setChecked(self.heatmap_plot_orientation.inv_y)
            self._rotate_button.setIcon(
                icons.ROTATE(rotated=-self.heatmap_plot_orientation.rotation)
            )
            self._set_2d_transforms(self.heatmap_plot_orientation)

        if config_changed:
            (min_range, max_range) = algo_utils.get_measured_range(state.session_config)

            self.cart_heatmap_plot_item.clear()
            self.cart_heatmap_plot_item.addItem(self.cart_heatmap_plot)
            self.cart_heatmap_plot_item.addItem(self._cart_peak_scatter)
            self.cart_heatmap_plot_item.addItem(self._cart_bounds_item)
            x_bounds = state.detection_volume.x_bounds_m
            y_bounds = state.detection_volume.y_bounds_m
            if x_bounds is not None and y_bounds is not None:
                x_lo, x_hi = x_bounds
                y_lo, y_hi = y_bounds
                self._cart_bounds_item.setData(
                    x=[x_lo, x_hi, x_hi, x_lo, x_lo],
                    y=[y_lo, y_lo, y_hi, y_hi, y_lo],
                )
                self._cart_bounds_item.setVisible(True)
            else:
                self._cart_bounds_item.setData([], [])
                self._cart_bounds_item.setVisible(False)
            self._set_2d_transforms(self.heatmap_plot_orientation)

            self.heatmap_gl_widget.clear()
            self.heatmap_gl_widget.addItem(self.axis_item)
            self.heatmap_gl_widget.addItem(self.x_axis_text_item)
            self.heatmap_gl_widget.addItem(self.y_axis_text_item)
            self.heatmap_gl_widget.addItem(self.z_axis_text_item)
            for item in self.sensor_model.items:
                self.heatmap_gl_widget.addItem(item)
            self.heatmap_gl_widget.addItem(self.sensor_text_item)
            self.heatmap_gl_widget.addItem(self._gl_peak_scatter)

            az_start = state.processor_config.effective_az_angle_range(state.detection_volume)[0]
            az_span = state.processor_config.az_span(state.detection_volume)
            el_angles = state.processor_config.el_angles(state.detection_volume)
            el_start = float(el_angles[0])
            el_span = float(el_angles[-1] - el_angles[0]) if len(el_angles) > 1 else 0.0
            mount_rotation = state.sensor_installation.mount_rotation.matrix
            self.sensor_model.set_mount_rotation(mount_rotation)
            _setup_spherical_coordinates(
                self.heatmap_gl_widget,
                az_start,
                az_span,
                el_start,
                el_span,
                max_range=max_range,
                min_range=min_range,
                rotation=mount_rotation,
            )
            _setup_detection_volume_box(
                self.heatmap_gl_widget, state.sensor_installation, state.detection_volume
            )

    def handle_message(self, message: GeneralMessage) -> None:
        if isinstance(message, backend.PlotMessage):
            self._plot_job = message.result
        else:
            raise NotImplementedError

    def draw(self) -> None:
        if self._plot_job is None:
            return

        proc_result = self._plot_job
        self._plot_job = None

        if proc_result is None or proc_result.heatmap is None:
            self._peak_history.clear()
            self._cart_peak_scatter.setData([], [])
            self._gl_peak_scatter.setData(pos=np.zeros((0, 3)))
            return

        heatmap_to_draw = np.nan_to_num(proc_result.heatmap, nan=0.0, posinf=1e20, neginf=0.0)

        draw_heatmap = self._heatmap_display_mode != HeatmapDisplayMode.HEATMAP_OFF
        mask_heatmap = self._heatmap_display_mode == HeatmapDisplayMode.HEATMAP_MASKED

        if draw_heatmap and not self.cart_heatmap_layout.isHidden():
            self._draw_2d_heatmap(
                heatmap_to_draw,
                proc_result.threshold_map,
                plot_fn=self.cart_heatmap_plot.setData,
                mask=mask_heatmap,
            )

        self._peak_history.append(proc_result.peaks)

        # Build per-point data with index-based alpha across all history frames
        cart_xs: list[float] = []
        cart_ys: list[float] = []
        gl_positions: list[list[float]] = []
        brushes_cart: list[pg.QtGui.QBrush] = []
        gl_colors: list[list[float]] = []

        n = len(self._peak_history)
        for i, peaks in enumerate(self._peak_history):
            fade = i / max(n - 1, 1)
            alpha_int = int(220 * fade)
            brush = pg.mkBrush(255, 50, 50, alpha_int)

            for p in peaks:
                x, y, z = p.cartesian_position
                cart_xs.append(x)
                cart_ys.append(y)
                brushes_cart.append(brush)
                gl_positions.append([x, y, z])
                gl_colors.append([1.0, 0.2, 0.2, fade])

        if cart_xs:
            self._cart_peak_scatter.setData(x=cart_xs, y=cart_ys, brush=brushes_cart, pen=None)
            self._gl_peak_scatter.setData(
                pos=np.array(gl_positions, dtype=np.float32),
                color=np.array(gl_colors, dtype=np.float32),
            )
        else:
            self._cart_peak_scatter.setData([], [])
            self._gl_peak_scatter.setData(pos=np.zeros((0, 3)))

    def _draw_2d_heatmap(
        self,
        heatmap_to_draw: npt.NDArray[np.float64],
        threshold_map: npt.NDArray[np.float64],
        plot_fn: t.Callable[..., t.Any],
        *,
        mask: bool,
    ) -> None:
        if self._processor_config is None or self._sensor_installation is None:
            return

        if self._sensor_installation.y_rotation == 180.0:
            heatmap_to_draw = heatmap_to_draw[:, ::-1]
            threshold_map = threshold_map[:, ::-1]

        heatmap_linear = np.nan_to_num(heatmap_to_draw.T, nan=0.0, posinf=1e20, neginf=0.0)

        heatmap_db = np.clip(heatmap_linear, a_min=0.0, a_max=None)
        heatmap_db = 10 * np.log10(heatmap_db + 1e-9)

        if mask:
            below_thresh = heatmap_linear < threshold_map.T
            heatmap_db[below_thresh] = _BELOW_THRESH_SENTINEL
            valid_db = heatmap_db[~below_thresh]
            level_min = _BELOW_THRESH_SENTINEL
        else:
            valid_db = heatmap_db
            level_min = 0.0

        max_heat_in_map = float(np.max(valid_db)) if valid_db.size > 0 else 0.0
        max_heat = float(self.heatmap_2d_plot_smooth_max.update(max_heat_in_map))
        max_heat = max(max_heat, max_heat_in_map, 1e-6)

        self.cart_heatmap_colorbar.setLevels((level_min, max_heat))

        image = copy.copy(heatmap_db)
        plot_fn(image, levels=(level_min, max_heat * 1.05))

    def _set_2d_transforms(self, heatmap_plot_orientation: HeatmapPlotOrientation) -> None:
        if (
            self._session_config is None
            or self._processor_config is None
            or self._sensor_installation is None
        ):
            return

        x_counter_inverted = heatmap_plot_orientation.rotation in [90, 180]
        y_counter_inverted = heatmap_plot_orientation.rotation in [180, 270]

        self._setup_axis(heatmap_plot_orientation)

        scale_and_rotate = (
            QTransform()
            .scale(
                -1.0 if x_counter_inverted else 1.0,
                -1.0 if y_counter_inverted else 1.0,
            )
            .rotate(heatmap_plot_orientation.rotation)
        )
        heatmap_transform = (
            QTransform().rotate(self._sensor_installation.z_rotation) * scale_and_rotate
        )
        self.cart_heatmap_plot.setTransform(heatmap_transform)
        self._cart_peak_scatter.setTransform(scale_and_rotate)
        self._cart_bounds_item.setTransform(scale_and_rotate)
        self.cart_heatmap_plot_item.autoRange()

    def _setup_axis(self, heatmap_plot_orientation: HeatmapPlotOrientation) -> None:
        invert_x = False
        invert_y = False

        self.cart_heatmap_plot_item.getAxis("left").setLabel("Y", units="m")
        self.cart_heatmap_plot_item.getAxis("bottom").setLabel("X", units="m")

        if heatmap_plot_orientation.rotation % 180 == 0:
            if heatmap_plot_orientation.rotation == 180:
                invert_x = not heatmap_plot_orientation.inv_x
                invert_y = not heatmap_plot_orientation.inv_y
            else:
                invert_x = heatmap_plot_orientation.inv_x
                invert_y = heatmap_plot_orientation.inv_y
        else:
            if heatmap_plot_orientation.rotation == 90:
                invert_x = not heatmap_plot_orientation.inv_x
                invert_y = heatmap_plot_orientation.inv_y
            else:
                invert_x = heatmap_plot_orientation.inv_x
                invert_y = not heatmap_plot_orientation.inv_y

        self.cart_heatmap_plot_item.invertX(b=invert_x)
        self.cart_heatmap_plot_item.invertY(b=invert_y)


def _setup_spherical_coordinates(
    view_widget: gl.GLViewWidget,
    az_start_deg: float,
    az_span_deg: float,
    el_start_deg: float,
    el_span_deg: float,
    max_range: float,
    min_range: float,
    circle_arc_segments: int = 100,
    rotation: npt.NDArray[np.float64] | None = None,
) -> None:
    def _rot(p: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        return rotation @ p if rotation is not None else p

    az_end_deg = az_start_deg + az_span_deg
    az_midpoint = (az_start_deg + az_end_deg) / 2.0
    el_end_deg = el_start_deg + el_span_deg
    degree = DEGREE_SYMBOL
    line_color = (0.5, 0.5, 0.5, 0.75)

    for el_line_angle in [el_start_deg, el_end_deg]:
        for az_line_angle in [az_start_deg, az_end_deg, az_midpoint]:
            start_pos = _rot(
                np.array(
                    et.utils.spherical_to_cartesian(
                        min_range,
                        np.radians(az_line_angle),
                        np.radians(el_line_angle),
                    )
                )
            )
            end_pos = _rot(
                np.array(
                    et.utils.spherical_to_cartesian(
                        max_range,
                        np.radians(az_line_angle),
                        np.radians(el_line_angle),
                    )
                )
            )
            line = gl.GLLinePlotItem(pos=np.array([start_pos, end_pos]), color=line_color)
            line.setGLOptions("opaque")
            view_widget.addItem(line)
            view_widget.addItem(
                gl.GLTextItem(
                    pos=1.1 * end_pos,
                    text=(
                        f"az, el = {az_line_angle:.1f}{degree}, {el_line_angle:.1f}{degree} "
                        f"{max_range:.2f} m"
                    ),
                    font=QFont("Helvetica", 7),
                    color=TEXT_COLOR,
                )
            )
            view_widget.addItem(
                gl.GLTextItem(
                    pos=1.1 * start_pos,
                    text=f"{min_range:.2f} m",
                    font=QFont("Helvetica", 7),
                    color=TEXT_COLOR,
                )
            )

    circle_arc_az = np.linspace(
        np.radians(az_start_deg), np.radians(az_end_deg), circle_arc_segments, endpoint=True
    ).reshape(-1, 1)
    az_start_arr = np.full_like(circle_arc_az, np.radians(az_start_deg))
    az_end_arr = np.full_like(circle_arc_az, np.radians(az_end_deg))
    circle_arc_el = np.linspace(
        np.radians(el_start_deg), np.radians(el_end_deg), circle_arc_segments, endpoint=True
    ).reshape(-1, 1)
    el_start_arr = np.full_like(circle_arc_el, np.radians(el_start_deg))
    el_end_arr = np.full_like(circle_arc_el, np.radians(el_end_deg))

    circle_arcs_angles = np.block(
        [
            [circle_arc_az, el_start_arr],
            [az_end_arr, circle_arc_el],
            [circle_arc_az[::-1], el_end_arr],
            [az_start_arr, circle_arc_el[::-1]],
        ]
    )

    pts_end = np.zeros((len(circle_arcs_angles), 3))
    pts_start = np.zeros((len(circle_arcs_angles), 3))
    for idx, (az, el) in enumerate(circle_arcs_angles):
        pts_end[idx] = _rot(np.array(et.utils.spherical_to_cartesian(max_range, az, el)))
        pts_start[idx] = _rot(np.array(et.utils.spherical_to_cartesian(min_range, az, el)))

    for pts in [pts_end, pts_start]:
        line = gl.GLLinePlotItem(pos=pts, color=line_color)
        line.setGLOptions("opaque")
        view_widget.addItem(line)


_VOLUME_BOX_COLOR = (0 / 255, 128 / 255, 255 / 255, 0.7)  # matches _BOUNDS_PEN

_VOLUME_BOX_EDGES = [
    (0, 1), (0, 2), (0, 4),
    (1, 3), (1, 5),
    (2, 3), (2, 6),
    (3, 7),
    (4, 5), (4, 6),
    (5, 7),
    (6, 7),
]  # fmt: skip


def _setup_detection_volume_box(
    view_widget: gl.GLViewWidget,
    sensor_installation: SensorInstallation,
    detection_volume: DetectionVolume,
) -> None:
    """Draw the detection volume's box as a 3D wireframe, if it has one, as
    high as ``sensor_installation``'s room.

    The bounds are Cartesian room extents in the world frame -- the same
    frame real detections are plotted in -- so the corners need no
    mapping, unlike the sensor-frame spherical grid drawn by
    ``_setup_spherical_coordinates``.
    """
    x_bounds = detection_volume.x_bounds_m
    y_bounds = detection_volume.y_bounds_m
    z_bounds = room_z_bounds_m(sensor_installation)
    if x_bounds is None or y_bounds is None:
        return
    corners = np.array([[x, y, z] for x in x_bounds for y in y_bounds for z in z_bounds])
    for i, j in _VOLUME_BOX_EDGES:
        line = gl.GLLinePlotItem(pos=corners[[i, j]], color=_VOLUME_BOX_COLOR, width=2)
        line.setGLOptions("opaque")
        view_widget.addItem(line)


@attrs.frozen(kw_only=True)
class ReplayDialogConfig:
    """The config edited before replaying a recording.

    The processor config is validated against the sensor installation and the
    detection volume as well as the session config, so the recording's are
    carried along.
    """

    processor_config: MotionDetectionConfig
    sensor_installation: SensorInstallation
    detection_volume: DetectionVolume

    def _collect_validation_results(
        self, session_config: a2.SessionConfig
    ) -> list[ValidationResult]:
        return self.processor_config._collect_validation_results(
            session_config, self.sensor_installation, self.detection_volume
        )


class ReplayDialogConfigEditor(DataEditor[ReplayDialogConfig | None]):
    """Edits the processor config of a :class:`ReplayDialogConfig`. The
    sensor installation and detection volume are passed through unchanged."""

    def __init__(self) -> None:
        super().__init__()
        self._geometry: tuple[SensorInstallation, DetectionVolume] | None = None
        self._processor_config_editor = AttrsConfigEditor(
            title="Motion Detection",
            factory_mapping=_pidget_mapping.get_motion_detection_config_pidget_mapping(),
            config_type=MotionDetectionConfig,
            save_load_buttons=False,
        )
        self._processor_config_editor.sig_update.connect(
            lambda _: self.sig_update.emit(self.get_data())
        )

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._processor_config_editor)
        self.setLayout(layout)

    def set_data(self, data: ReplayDialogConfig | None) -> None:
        if data is None:
            self._geometry = None
            self._processor_config_editor.set_data(None)
        else:
            self._geometry = (data.sensor_installation, data.detection_volume)
            self._processor_config_editor.set_data(data.processor_config)

    def get_data(self) -> ReplayDialogConfig | None:
        processor_config = self._processor_config_editor.get_data()
        if processor_config is None or self._geometry is None:
            return None
        sensor_installation, detection_volume = self._geometry
        return ReplayDialogConfig(
            processor_config=processor_config,
            sensor_installation=sensor_installation,
            detection_volume=detection_volume,
        )

    def handle_validation_results(self, results: list[ValidationResult]) -> list[ValidationResult]:
        return self._processor_config_editor.handle_validation_results(results)

    @property
    def is_ready(self) -> bool:
        return self._processor_config_editor.is_ready


def _replay_dialog_get_config(
    path: Path,
) -> tuple[t.Literal["default", "loaded"], ReplayDialogConfig, a2.SessionConfig]:
    with a2.open_record(path) as record:
        session_config = record.session_config
        try:
            algo_group = record.require_algo_group(ALGO_GROUP_NAME)
            geometry = load_detection_geometry(algo_group)
            if geometry is None:
                msg = "No sensor installation or detection volume in the recording."
                raise KeyError(msg)
            sensor_installation, detection_volume = geometry
        except Exception:
            log.warning(
                "Could not load sensor installation or detection volume from recording; "
                "using default.",
                exc_info=False,
            )
            _, _, sensor_installation, detection_volume = get_walking_detection_configs()

        try:
            algo_group = record.require_algo_group(ALGO_GROUP_NAME)
            processor_config = MotionDetectionConfig.from_json(
                algo_group[PROCESSOR_CONFIG_DATASET_NAME][()].decode()
            )
            processor_config.validate(session_config, sensor_installation, detection_volume)
            config_source: t.Literal["default", "loaded"] = "loaded"
        except Exception:
            log.warning(
                "Could not load processor config from recording; using default.",
                exc_info=False,
            )
            processor_config, _, _, _ = get_walking_detection_configs()
            config_source = "default"

        replay_dialog_config = ReplayDialogConfig(
            processor_config=processor_config,
            sensor_installation=sensor_installation,
            detection_volume=detection_volume,
        )
        return (config_source, replay_dialog_config, session_config)
