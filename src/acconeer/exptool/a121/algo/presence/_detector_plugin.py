# Copyright (c) Acconeer AB, 2022-2025
# All rights reserved

from __future__ import annotations

import logging
from enum import Enum, auto
from typing import Any, Callable, Mapping, Optional

import attrs
import h5py
import numpy as np

from PySide6 import QtCore
from PySide6.QtWidgets import QPushButton, QVBoxLayout

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121._h5_utils import _create_h5_string_dataset
from acconeer.exptool.a121.algo._plugins import (
    A121BackendPluginBase,
    A121ViewPluginBase,
)
from acconeer.exptool.app.new import (
    AppModel,
    AttrsConfigEditor,
    BackendLogger,
    GeneralMessage,
    GroupBox,
    Message,
    MiscErrorView,
    PgPlotPlugin,
    PidgetGroupFactoryMapping,
    PluginFamily,
    PluginGeneration,
    PluginPresetBase,
    PluginSpecBase,
    backend,
    icons,
    is_task,
    pidgets,
    visual_policies,
)
from acconeer.exptool.app.new.ui.components import CollapsibleWidget, GotoResourceTabButton
from acconeer.exptool.app.new.ui.components.a121 import (
    SensorConfigEditor,
)
from acconeer.exptool.app.new.ui.components.json_save_load_buttons import PresentationType

from . import _pidget_mapping
from ._configs import (
    get_long_range_config,
    get_low_power_config,
    get_medium_range_config,
    get_short_range_config,
)
from ._detector import (
    Detector,
    DetectorConfig,
    DetectorContext,
    DetectorMetadata,
    DetectorResult,
    _load_algo_data,
)


log = logging.getLogger(__name__)


@attrs.mutable(kw_only=True)
class SharedState:
    sensor_id: int = attrs.field(default=1)
    config: DetectorConfig = attrs.field(factory=DetectorConfig)
    context: Optional[DetectorContext] = attrs.field(default=None)


class PluginPresetId(Enum):
    SHORT_RANGE = auto()
    MEDIUM_RANGE = auto()
    LONG_RANGE = auto()
    LOW_POWER = auto()


@attrs.frozen(kw_only=True)
class SetupMessage(GeneralMessage):
    detector_config: DetectorConfig
    detector_metadata: DetectorMetadata
    estimated_frame_rate: float
    name: str = attrs.field(default="setup", init=False)
    recipient: backend.RecipientLiteral = attrs.field(default="plot_plugin", init=False)


class BackendPlugin(A121BackendPluginBase[SharedState]):
    PLUGIN_PRESETS: Mapping[int, Callable[[], DetectorConfig]] = {
        PluginPresetId.SHORT_RANGE.value: lambda: get_short_range_config(),
        PluginPresetId.MEDIUM_RANGE.value: lambda: get_medium_range_config(),
        PluginPresetId.LONG_RANGE.value: lambda: get_long_range_config(),
        PluginPresetId.LOW_POWER.value: lambda: get_low_power_config(),
    }

    def __init__(
        self, callback: Callable[[Message], None], generation: PluginGeneration, key: str
    ) -> None:
        super().__init__(callback=callback, generation=generation, key=key)

        self._recorder: Optional[a121.H5Recorder] = None
        self._detector_instance: Optional[Detector] = None
        self._log = BackendLogger.getLogger(__name__)

        self.restore_defaults()

    def _load_from_cache(self, file: h5py.File) -> None:
        self.shared_state.config = DetectorConfig.from_json(file["config"][()])

    @is_task
    def restore_defaults(self) -> None:
        self.shared_state = SharedState(config=get_medium_range_config())
        self.broadcast()

    @is_task
    def update_sensor_id(self, *, sensor_id: int) -> None:
        self.shared_state.sensor_id = sensor_id
        self.broadcast()

    def _sync_sensor_ids(self) -> None:
        if self.client is not None:
            sensor_ids = self.client.server_info.connected_sensors

            if len(sensor_ids) > 0 and self.shared_state.sensor_id not in sensor_ids:
                self.shared_state.sensor_id = sensor_ids[0]

    @is_task
    def update_config(self, *, config: DetectorConfig) -> None:
        self.shared_state.config = config
        self.broadcast()

    def save_to_cache(self, file: h5py.File) -> None:
        _create_h5_string_dataset(file, "config", self.shared_state.config.to_json())

    @is_task
    def set_preset(self, preset_id: int) -> None:
        preset_config = self.PLUGIN_PRESETS[preset_id]
        self.shared_state.config = preset_config()
        self.broadcast()

    def load_from_record_setup(self, *, record: a121.H5Record) -> None:
        algo_group = record.get_algo_group(self.key)
        _, config, context = _load_algo_data(algo_group)
        self.shared_state.config = config
        self.shared_state.context = context
        self.shared_state.sensor_id = record.sensor_id

    def _start_session(self, recorder: Optional[a121.H5Recorder]) -> None:
        assert self.client
        self._detector_instance = Detector(
            client=self.client,
            sensor_id=self.shared_state.sensor_id,
            detector_config=self.shared_state.config,
            detector_context=self.shared_state.context,
        )
        self._detector_instance.start(recorder)
        assert self._detector_instance.detector_metadata is not None
        self.callback(
            SetupMessage(
                detector_config=self.shared_state.config,
                detector_metadata=self._detector_instance.detector_metadata,
                estimated_frame_rate=self._detector_instance.estimated_frame_rate,
            )
        )

    def end_session(self) -> None:
        if self._detector_instance is None:
            raise RuntimeError
        if self._recorder is not None:
            self._recorder.close()
        self._detector_instance.stop()

    def get_next(self) -> None:
        assert self.client
        if self._detector_instance is None:
            raise RuntimeError
        result = self._detector_instance.get_next()

        self.callback(backend.PlotMessage(result=result))


class PlotPlugin(PgPlotPlugin):
    def __init__(self, app_model: AppModel) -> None:
        super().__init__(app_model=app_model)
        self._plot_job: Optional[DetectorResult] = None
        self._is_setup = False

    def handle_message(self, message: backend.GeneralMessage) -> None:
        if isinstance(message, backend.PlotMessage):
            self._plot_job = message.result
        elif isinstance(message, SetupMessage):
            self.setup(
                detector_config=message.detector_config,
                detector_metadata=message.detector_metadata,
                estimated_frame_rate=message.estimated_frame_rate,
            )
            self._is_setup = True
        else:
            log.warn(f"{self.__class__.__name__} got an unsupported command: {message.name!r}.")

    def draw(self) -> None:
        if not self._is_setup or self._plot_job is None:
            return

        try:
            self.draw_plot_job(self._plot_job)
        finally:
            self._plot_job = None

    def setup(
        self,
        detector_config: DetectorConfig,
        detector_metadata: DetectorMetadata,
        estimated_frame_rate: float,
    ) -> None:
        self.plot_layout.clear()

        self.detector_config = detector_config
        self.distances = np.linspace(
            detector_metadata.start_m,
            detector_config.end_m,
            detector_metadata.num_points,
        )

        self.history_length_s = 5
        self.history_length_n = int(round(self.history_length_s * estimated_frame_rate))
        self.intra_history = np.zeros(self.history_length_n)
        self.inter_history = np.zeros(self.history_length_n)

        win = self.plot_layout

        self.intra_limit_lines = []
        self.inter_limit_lines = []

        # Noise estimation plot

        self.noise_plot = win.addPlot(
            row=0,
            col=0,
            title="Noise",
        )
        self.noise_plot.setMenuEnabled(False)
        self.noise_plot.setMouseEnabled(x=False, y=False)
        self.noise_plot.hideButtons()
        self.noise_plot.showGrid(x=True, y=True)
        self.noise_plot.setLabel("bottom", "Distance (m)")
        self.noise_plot.setLabel("left", "Amplitude")
        self.noise_plot.setVisible(False)
        self.noise_curve = self.noise_plot.plot(pen=et.utils.pg_pen_cycler())
        self.noise_smooth_max = et.utils.SmoothMax(self.detector_config.frame_rate)

        # Depthwise presence plot

        self.move_plot = pg.PlotItem(title="Depthwise presence")
        self.move_plot.setMenuEnabled(False)
        self.move_plot.setMouseEnabled(x=False, y=False)
        self.move_plot.hideButtons()
        self.move_plot.showGrid(x=True, y=True)
        self.move_plot.setLabel("bottom", "Distance (m)")
        self.move_plot.setLabel("left", "Norm. ampl.")
        self.move_plot.setXRange(self.distances[0], self.distances[-1])
        self.intra_curve = self.move_plot.plot(pen=et.utils.pg_pen_cycler(1))
        if not self.detector_config.intra_enable:
            self.intra_curve.hide()

        self.inter_curve = self.move_plot.plot(pen=et.utils.pg_pen_cycler(0))
        if not self.detector_config.inter_enable:
            self.inter_curve.hide()

        self.move_smooth_max = et.utils.SmoothMax(
            self.detector_config.frame_rate,
            tau_decay=1.0,
            tau_grow=0.25,
        )

        self.move_depth_line = pg.InfiniteLine(pen=pg.mkPen("k", width=1.5))
        self.move_depth_line.hide()
        self.move_plot.addItem(self.move_depth_line)

        self.present_html_format = (
            '<div style="text-align: center">'
            '<span style="color: #FFFFFF;font-size:15pt;">'
            "{}</span></div>"
        )
        not_present_html = (
            '<div style="text-align: center">'
            '<span style="color: #FFFFFF;font-size:15pt;">'
            "{}</span></div>".format("No presence detected")
        )
        self.present_text_item = pg.TextItem(
            fill=pg.mkColor(0xFF, 0x7F, 0x0E, 200),
            anchor=(0.5, 0),
        )
        self.not_present_text_item = pg.TextItem(
            html=not_present_html,
            fill=pg.mkColor(0x1F, 0x77, 0xB4, 180),
            anchor=(0.5, 0),
        )

        self.move_plot.addItem(self.present_text_item)
        self.move_plot.addItem(self.not_present_text_item)
        self.present_text_item.hide()
        self.not_present_text_item.hide()

        # Intra presence history plot

        self.intra_hist_plot = win.addPlot(
            row=1,
            col=0,
            title="Intra presence history (fast motions)",
        )
        self.intra_hist_plot.setMenuEnabled(False)
        self.intra_hist_plot.setMouseEnabled(x=False, y=False)
        self.intra_hist_plot.hideButtons()
        self.intra_hist_plot.showGrid(x=True, y=True)
        self.intra_hist_plot.setLabel("bottom", "Time (s)")
        self.intra_hist_plot.setLabel("left", "Score")
        self.intra_hist_plot.setXRange(-self.history_length_s, 0)
        self.intra_history_smooth_max = et.utils.SmoothMax(self.detector_config.frame_rate)
        self.intra_hist_plot.setYRange(0, 10)
        if not self.detector_config.intra_enable:
            intra_color = et.utils.color_cycler(1)
            intra_color = f"{intra_color}50"
            intra_dashed_pen = pg.mkPen(intra_color, width=2.5, style=QtCore.Qt.PenStyle.DashLine)
            intra_pen = pg.mkPen(intra_color, width=2)
        else:
            intra_dashed_pen = et.utils.pg_pen_cycler(1, width=2.5, style="--")
            intra_pen = et.utils.pg_pen_cycler(1)

        self.intra_hist_curve = self.intra_hist_plot.plot(pen=intra_pen)
        limit_line = pg.InfiniteLine(angle=0, pen=intra_dashed_pen)
        self.intra_hist_plot.addItem(limit_line)
        self.intra_limit_lines.append(limit_line)

        for line in self.intra_limit_lines:
            line.setPos(self.detector_config.intra_detection_threshold)

        # Inter presence history plot

        self.inter_hist_plot = win.addPlot(
            row=1,
            col=1,
            title="Inter presence history (slow motions)",
        )
        self.inter_hist_plot.setMenuEnabled(False)
        self.inter_hist_plot.setMouseEnabled(x=False, y=False)
        self.inter_hist_plot.hideButtons()
        self.inter_hist_plot.showGrid(x=True, y=True)
        self.inter_hist_plot.setLabel("bottom", "Time (s)")
        self.inter_hist_plot.setLabel("left", "Score")
        self.inter_hist_plot.setXRange(-self.history_length_s, 0)
        self.inter_history_smooth_max = et.utils.SmoothMax(self.detector_config.frame_rate)
        self.inter_hist_plot.setYRange(0, 10)
        if not self.detector_config.inter_enable:
            inter_color = et.utils.color_cycler(0)
            inter_color = f"{inter_color}50"
            inter_dashed_pen = pg.mkPen(inter_color, width=2.5, style=QtCore.Qt.PenStyle.DashLine)
            inter_pen = pg.mkPen(inter_color, width=2)
        else:
            inter_pen = et.utils.pg_pen_cycler(0)
            inter_dashed_pen = et.utils.pg_pen_cycler(0, width=2.5, style="--")

        self.inter_hist_curve = self.inter_hist_plot.plot(pen=inter_pen)
        limit_line = pg.InfiniteLine(angle=0, pen=inter_dashed_pen)
        self.inter_hist_plot.addItem(limit_line)
        self.inter_limit_lines.append(limit_line)

        for line in self.inter_limit_lines:
            line.setPos(self.detector_config.inter_detection_threshold)

        sublayout = win.addLayout(row=2, col=0, colspan=2)
        sublayout.layout.setColumnStretchFactor(0, 2)
        sublayout.addItem(self.move_plot, row=0, col=0)

    def draw_plot_job(self, data: DetectorResult) -> None:
        noise = data.processor_extra_result.lp_noise
        self.noise_curve.setData(self.distances, noise)
        self.noise_plot.setYRange(0, self.noise_smooth_max.update(noise))

        movement_x = data.presence_distance

        self.inter_curve.setData(self.distances, data.inter_depthwise_scores)
        self.intra_curve.setData(self.distances, data.intra_depthwise_scores)
        m = self.move_smooth_max.update(
            np.max(np.maximum(data.inter_depthwise_scores, data.intra_depthwise_scores))
        )
        m = max(
            m,
            2
            * np.maximum(
                self.detector_config.intra_detection_threshold,
                self.detector_config.inter_detection_threshold,
            ),
        )
        self.move_plot.setYRange(0, m)
        self.move_depth_line.setPos(movement_x)
        self.move_depth_line.setVisible(bool(data.presence_detected))

        self.set_present_text_y_pos(m)

        if data.presence_detected:
            present_text = "Presence detected at {:.0f} cm".format(movement_x * 100)
            present_html = self.present_html_format.format(present_text)
            self.present_text_item.setHtml(present_html)

            self.present_text_item.show()
            self.not_present_text_item.hide()
        else:
            self.present_text_item.hide()
            self.not_present_text_item.show()

        # Intra presence

        move_hist_xs = np.linspace(-self.history_length_s, 0, self.history_length_n)

        self.intra_history = np.roll(self.intra_history, -1)
        self.intra_history[-1] = data.intra_presence_score

        m_hist = max(
            float(np.max(self.intra_history)),
            self.detector_config.intra_detection_threshold * 1.05,
        )
        m_hist = self.intra_history_smooth_max.update(m_hist)

        self.intra_hist_plot.setYRange(0, m_hist)
        self.intra_hist_curve.setData(move_hist_xs, self.intra_history)

        # Inter presence

        self.inter_history = np.roll(self.inter_history, -1)
        self.inter_history[-1] = data.inter_presence_score

        m_hist = max(
            float(np.max(self.inter_history)),
            self.detector_config.inter_detection_threshold * 1.05,
        )
        m_hist = self.inter_history_smooth_max.update(m_hist)

        self.inter_hist_plot.setYRange(0, m_hist)
        self.inter_hist_curve.setData(move_hist_xs, self.inter_history)

    def set_present_text_y_pos(self, y: float) -> None:
        x_pos = self.distances[0] + (self.distances[-1] - self.distances[0]) / 2
        self.present_text_item.setPos(x_pos, 0.95 * y)
        self.not_present_text_item.setPos(x_pos, 0.95 * y)


class ViewPlugin(A121ViewPluginBase):
    def __init__(self, app_model: AppModel) -> None:
        super().__init__(app_model=app_model)
        self._log = logging.getLogger(__name__)

        self.start_button = QPushButton(icons.PLAY(), "Start measurement")
        self.start_button.setShortcut("space")
        self.start_button.setToolTip("Starts the session.\n\nShortcut: Space")
        self.start_button.clicked.connect(self._send_start_request)

        self.stop_button = QPushButton(icons.STOP(), "Stop")
        self.stop_button.setShortcut("space")
        self.stop_button.setToolTip("Stops the session.\n\nShortcut: Space")
        self.stop_button.clicked.connect(self._send_stop_request)

        button_group = GroupBox.grid("Controls", parent=self.sticky_widget)
        button_group.layout().addWidget(self.start_button, 0, 0)
        button_group.layout().addWidget(self.stop_button, 0, 1)

        self.misc_error_view = MiscErrorView(self.scrolly_widget)

        sensor_selection_group = GroupBox.vertical("Sensor selection", parent=self.scrolly_widget)
        self.sensor_id_pidget = pidgets.SensorIdPidgetFactory(items=[]).create(
            parent=sensor_selection_group
        )
        self.sensor_id_pidget.sig_update.connect(self._on_sensor_id_update)
        sensor_selection_group.layout().addWidget(self.sensor_id_pidget)

        self.config_editor = AttrsConfigEditor(
            title="Detector parameters",
            factory_mapping=self._get_pidget_mapping(),
            config_type=DetectorConfig,
            extra_presenter=_set_config_presenter,
            parent=self.scrolly_widget,
        )
        self.config_editor.sig_update.connect(self._on_config_update)

        goto_resource_tab_button = GotoResourceTabButton()
        goto_resource_tab_button.clicked.connect(
            lambda: app_model.sig_resource_tab_input_block_requested.emit(
                self.config_editor.get_data()
            )
        )

        sticky_layout = QVBoxLayout()
        sticky_layout.setContentsMargins(0, 0, 0, 0)

        sticky_layout.addWidget(button_group)

        scrolly_layout = QVBoxLayout()
        scrolly_layout.setContentsMargins(0, 0, 0, 0)

        self.sensor_config_status = SensorConfigEditor()
        self.sensor_config_status.set_read_only(True)
        collapsible_widget = CollapsibleWidget(
            "Current sensor settings", self.sensor_config_status, self.scrolly_widget
        )

        scrolly_layout.addWidget(goto_resource_tab_button)
        scrolly_layout.addWidget(self.misc_error_view)
        scrolly_layout.addWidget(sensor_selection_group)
        scrolly_layout.addWidget(collapsible_widget)
        scrolly_layout.addWidget(self.config_editor)

        self.sticky_widget.setLayout(sticky_layout)
        self.scrolly_widget.setLayout(scrolly_layout)

    @classmethod
    def _get_pidget_mapping(cls) -> PidgetGroupFactoryMapping:
        return _pidget_mapping.get_pidget_mapping()

    def on_backend_state_update(self, state: Optional[SharedState]) -> None:
        if state is None:
            self.config_editor.set_data(None)
            self.sensor_config_status.set_data(None)
        else:
            self.config_editor.set_data(state.config)
            self.sensor_id_pidget.set_data(state.sensor_id)

            results = state.config._collect_validation_results()

            not_handled = self.config_editor.handle_validation_results(results)

            not_handled = self.misc_error_view.handle_validation_results(not_handled)

            assert not_handled == []

            if len(results) == 0:
                sensor_config = Detector._get_sensor_config(state.config)

                self.sensor_config_status.set_data(sensor_config)

    def on_app_model_update(self, app_model: AppModel) -> None:
        self.sensor_id_pidget.set_selectable_sensors(app_model.connected_sensors)

        self.start_button.setEnabled(
            visual_policies.start_button_enabled(
                app_model, extra_condition=self.config_editor.is_ready
            )
        )
        self.stop_button.setEnabled(visual_policies.stop_button_enabled(app_model))

        visual_policies.apply_enabled_policy(
            visual_policies.config_editor_enabled,
            app_model,
            widgets=[self.config_editor, self.sensor_id_pidget],
        )

    def _on_config_update(self, config: DetectorConfig) -> None:
        BackendPlugin.update_config.rpc(self.app_model.put_task, config=config)

    def _send_defaults_request(self) -> None:
        BackendPlugin.restore_defaults.rpc(self.app_model.put_task)

    def _on_sensor_id_update(self, sensor_id: int) -> None:
        BackendPlugin.update_sensor_id.rpc(self.app_model.put_task, sensor_id=sensor_id)


def _set_config_presenter(config: Any, presentation_type: PresentationType) -> Optional[str]:
    if isinstance(config, DetectorConfig) and presentation_type is PresentationType.C_SET_CONFIG:
        step_length_call = (
            "acc_detector_presence_config_auto_step_length_set(config, true)"
            if config.step_length is None
            else f"acc_detector_presence_config_step_length_set(config, {config.step_length}U)"
        )
        profile_call = (
            "acc_detector_presence_config_auto_profile_set(config, true)"
            if config.profile is None
            else f"acc_detector_presence_config_profile_set(config, {config.profile}U)"
        )
        intra = config.intra_enable
        inter = config.inter_enable
        intra_comment = "// " if not intra else ""
        inter_comment = "// " if not inter else ""

        return f"""
static void set_config(acc_detector_presence_config_t *config, presence_preset_config_t preset)
{{
    // This snippet is generated to be compatible with RSS A121 v1.0.0
    // If there is a version missmatch the snippet might need some modification

    (void)preset;

    acc_detector_presence_config_sensor_set(config, SENSOR_ID);

    acc_detector_presence_config_start_set(config, {config.start_m:.3f}f);
    acc_detector_presence_config_end_set(config, {config.end_m:.3f}f);
    {profile_call};
    {step_length_call};
    acc_detector_presence_config_sweeps_per_frame_set(config, {config.sweeps_per_frame}U);
    acc_detector_presence_config_hwaas_set(config, {config.hwaas}U);

    acc_detector_presence_config_frame_rate_set(config, {config.frame_rate:.3f}f);
    acc_detector_presence_config_inter_frame_idle_state_set(config, ACC_CONFIG_IDLE_STATE_{config.inter_frame_idle_state.name});

    acc_detector_presence_config_intra_detection_set(config, {str(config.intra_enable).lower()});
    {intra_comment}acc_detector_presence_config_intra_detection_threshold_set(config, {config.intra_detection_threshold:.3f}f);
    {intra_comment}acc_detector_presence_config_intra_frame_time_const_set(config, {config.intra_frame_time_const:.3f}f);
    {intra_comment}acc_detector_presence_config_intra_output_time_const_set(config, {config.intra_output_time_const:.3f}f);


    acc_detector_presence_config_inter_detection_set(config, {str(config.inter_enable).lower()});
    {inter_comment}acc_detector_presence_config_inter_detection_threshold_set(config, {config.inter_detection_threshold:.3f}f);
    {inter_comment}acc_detector_presence_config_inter_frame_fast_cutoff_set(config, {config.inter_frame_fast_cutoff:.3f}f);
    {inter_comment}acc_detector_presence_config_inter_frame_slow_cutoff_set(config, {config.inter_frame_slow_cutoff:.3f}f);
    {inter_comment}acc_detector_presence_config_inter_frame_deviation_time_const_set(config, {config.inter_frame_deviation_time_const:.3f}f);
    {inter_comment}acc_detector_presence_config_inter_output_time_const_set(config, {config.inter_output_time_const:.3f});
    {inter_comment}acc_detector_presence_config_inter_frame_presence_timeout_set(config, {config.inter_frame_presence_timeout or 0.0:.3f}f);

    // This parameter is needed if the sensor is put in HIBERNATE or OFF.
    // For more information, see the Presence Detector User Guide:
    //
    // https://developer.acconeer.com
    // Documents and learning > A121 > SW > A121 Presence Detector User Guide
    //
    // acc_detector_presence_config_frame_rate_app_driven_set(config, true);
}}
"""

    return None


class PluginSpec(PluginSpecBase):
    def create_backend_plugin(
        self, callback: Callable[[Message], None], key: str
    ) -> BackendPlugin:
        return BackendPlugin(callback=callback, generation=self.generation, key=key)

    def create_view_plugin(self, app_model: AppModel) -> ViewPlugin:
        return ViewPlugin(app_model=app_model)

    def create_plot_plugin(self, app_model: AppModel) -> PlotPlugin:
        return PlotPlugin(app_model=app_model)


PRESENCE_DETECTOR_PLUGIN = PluginSpec(
    generation=PluginGeneration.A121,
    key="presence_detector",
    title="Presence detector",
    docs_link="https://docs.acconeer.com/en/latest/detectors/a121/presence_detector.html",
    description="Detect human presence.",
    family=PluginFamily.DETECTOR,
    presets=[
        PluginPresetBase(
            name="Short range",
            description="Short range",
            preset_id=PluginPresetId.SHORT_RANGE,
        ),
        PluginPresetBase(
            name="Medium range",
            description="Medium range",
            preset_id=PluginPresetId.MEDIUM_RANGE,
        ),
        PluginPresetBase(
            name="Long range",
            description="Long range",
            preset_id=PluginPresetId.LONG_RANGE,
        ),
        PluginPresetBase(
            name="Low power, Wake up",
            description="Low power presence detection, which can be used as a trigger",
            preset_id=PluginPresetId.LOW_POWER,
        ),
    ],
    default_preset_id=PluginPresetId.MEDIUM_RANGE,
)
