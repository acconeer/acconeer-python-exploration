# Copyright (c) Acconeer AB, 2022-2025
# All rights reserved

from __future__ import annotations

import contextlib
import logging
from enum import Enum, auto
from typing import Any, Callable, Mapping, Optional

import attrs
import h5py
import numpy as np

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QPushButton, QTabWidget, QVBoxLayout

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121, opser
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
    HandledException,
    Message,
    MiscErrorView,
    PgPlotPlugin,
    PidgetFactoryMapping,
    PluginFamily,
    PluginGeneration,
    PluginPresetBase,
    PluginSpecBase,
    PluginState,
    PluginStateMessage,
    backend,
    icons,
    is_task,
    pidgets,
    visual_policies,
)
from acconeer.exptool.app.new.ui.components import (
    CollapsibleWidget,
    GotoResourceTabButton,
)
from acconeer.exptool.app.new.ui.components.a121 import SensorConfigEditor
from acconeer.exptool.app.new.ui.components.json_save_load_buttons import (
    JsonButtonOperations,
    PresentationType,
)

from . import _pidget_mapping
from ._configs import get_high_accuracy_detector_config
from ._context import detector_context_timeline
from ._detector import (
    DetailedStatus,
    Detector,
    DetectorConfig,
    DetectorContext,
    DetectorResult,
    _load_algo_data,
)
from ._translation import detector_config_to_session_config


log = logging.getLogger(__name__)


@attrs.mutable(kw_only=True)
class SharedState:
    sensor_ids: list[int] = attrs.field(factory=lambda: [1])
    config: DetectorConfig = attrs.field(factory=DetectorConfig)
    context: DetectorContext = attrs.field(factory=DetectorContext)


class PluginPresetId(Enum):
    BALANCED = auto()
    HIGH_ACCURACY = auto()


@attrs.frozen(kw_only=True)
class SetupMessage(GeneralMessage):
    num_curves: int
    start_m: float
    end_m: float
    name: str = attrs.field(default="setup", init=False)
    recipient: backend.RecipientLiteral = attrs.field(default="plot_plugin", init=False)


class BackendPlugin(A121BackendPluginBase[SharedState]):
    PLUGIN_PRESETS: Mapping[int, Callable[[], DetectorConfig]] = {
        PluginPresetId.BALANCED.value: lambda: DetectorConfig(),
        PluginPresetId.HIGH_ACCURACY.value: lambda: get_high_accuracy_detector_config(),
    }

    def __init__(
        self, callback: Callable[[Message], None], generation: PluginGeneration, key: str
    ) -> None:
        super().__init__(callback=callback, generation=generation, key=key)
        self._detector_instance: Optional[Detector] = None
        self._log = BackendLogger.getLogger(__name__)

        self.restore_defaults()

    @is_task
    def restore_defaults(self) -> None:
        self.shared_state = SharedState()
        self.broadcast()

    def _sync_sensor_ids(self) -> None:
        if self.client is not None:
            sensor_ids = self.client.server_info.connected_sensors

            # Try to use the sensor ids from the last calibration
            if self.shared_state.context.sensor_ids:
                self.shared_state.sensor_ids = self.shared_state.context.sensor_ids

            for i in range(len(self.shared_state.sensor_ids)):
                if len(sensor_ids) > 0 and self.shared_state.sensor_ids[i] not in sensor_ids:
                    self.shared_state.sensor_ids[i] = sensor_ids[0]

    @is_task
    def update_config(self, *, config: DetectorConfig) -> None:
        self.shared_state.config = config
        self.broadcast()

    @is_task
    def update_sensor_ids(self, *, sensor_ids: list[int]) -> None:
        self.shared_state.sensor_ids = sensor_ids
        self.broadcast()

    @is_task
    def set_preset(self, preset_id: int) -> None:
        preset_config = self.PLUGIN_PRESETS[preset_id]
        self.shared_state.config = preset_config()
        self.broadcast()

    def save_to_cache(self, file: h5py.File) -> None:
        _create_h5_string_dataset(file, "config", self.shared_state.config.to_json())
        context_group = file.create_group("context")
        opser.serialize(self.shared_state.context, context_group)

    def _load_from_cache(self, file: h5py.File) -> None:
        self.shared_state.config = DetectorConfig.from_json(file["config"][()])
        self.shared_state.context = detector_context_timeline.migrate(file["context"])

    def load_from_record_setup(self, *, record: a121.H5Record) -> None:
        algo_group = record.get_algo_group(self.key)
        _, config, context = _load_algo_data(algo_group)
        self.shared_state.config = config
        self.shared_state.context = context
        self.shared_state.sensor_ids = list(next(iter(record.session_config.groups)).keys())

    def _start_session(self, recorder: Optional[a121.H5Recorder]) -> None:
        assert self.client
        self._detector_instance = Detector(
            client=self.client,
            sensor_ids=self.shared_state.sensor_ids,
            detector_config=self.shared_state.config,
            context=self.shared_state.context,
        )
        self._detector_instance.start(recorder)
        self.callback(
            SetupMessage(
                num_curves=len(self._detector_instance.processor_specs),
                start_m=self.shared_state.config.start_m,
                end_m=self.shared_state.config.end_m,
            )
        )

    def end_session(self) -> None:
        assert self._detector_instance
        if self._recorder is not None:
            self._recorder.close()
        self._detector_instance.stop()

    def get_next(self) -> None:
        if self._detector_instance is None:
            raise RuntimeError

        assert self.client
        result = self._detector_instance.get_next()

        self.callback(backend.PlotMessage(result=result))

    @is_task
    def calibrate_detector(self) -> None:
        if self._started:
            raise RuntimeError

        if self.client is None:
            raise RuntimeError

        if not self.client.connected:
            raise RuntimeError

        self.callback(PluginStateMessage(state=PluginState.LOADED_BUSY))

        try:
            self._detector_instance = Detector(
                client=self.client,
                sensor_ids=self.shared_state.sensor_ids,
                detector_config=self.shared_state.config,
                context=None,
            )
            self._detector_instance.calibrate_detector()
        except Exception as exc:
            msg = "Failed to calibrate detector"
            raise HandledException(msg) from exc
        finally:
            self.callback(PluginStateMessage(state=PluginState.LOADED_IDLE))

        self.shared_state.context = self._detector_instance.context
        self.broadcast()


class PlotPlugin(PgPlotPlugin):
    _DISTANCE_HISTORY_SPAN_MARGIN = 0.05
    _DISTANCE_HISTORY_LEN = 100
    _MAX_NUM_MINOR_PEAKS = 4

    def __init__(self, app_model: AppModel) -> None:
        super().__init__(app_model=app_model)
        self._plot_job: Optional[dict[int, DetectorResult]] = None
        self._is_setup = False

    def handle_message(self, message: backend.GeneralMessage) -> None:
        if isinstance(message, backend.PlotMessage):
            self._plot_job = message.result
        elif isinstance(message, SetupMessage):
            self.setup(message.num_curves, message.start_m, message.end_m)
            self._is_setup = True
        else:
            log.warn(f"{self.__class__.__name__} got an unsupported command: {message.name!r}.")

    def draw(self) -> None:
        if not self._is_setup or self._plot_job is None:
            return

        try:
            self.draw_plot_job(multi_sensor_result=self._plot_job)
        finally:
            self._plot_job = None

    def setup(self, num_curves: int, start_m: float, end_m: float) -> None:
        self.plot_layout.clear()

        self.num_curves = num_curves
        self.start_m = start_m
        self.end_m = end_m

        self.main_peak_history = np.full(self._DISTANCE_HISTORY_LEN, fill_value=np.nan)
        self.minor_peaks_history = np.full(
            (self._MAX_NUM_MINOR_PEAKS, self._DISTANCE_HISTORY_LEN), fill_value=np.nan
        )

        win = self.plot_layout

        # Sweep plot
        self.sweep_plot = win.addPlot(row=0, col=0)
        self.sweep_plot.setMenuEnabled(False)
        self.sweep_plot.showGrid(x=True, y=True)
        self.sweep_plot.addLegend()
        self.sweep_plot.setLabel("left", "Amplitude")
        self.sweep_plot.setLabel("bottom", "Distance (m)")
        self.sweep_plot.addItem(pg.PlotDataItem())

        pen = et.utils.pg_pen_cycler(0)
        brush = et.utils.pg_brush_cycler(0)
        symbol_kw = dict(symbol="o", symbolSize=1, symbolBrush=brush, symbolPen="k")
        feat_kw = dict(pen=pen, **symbol_kw)
        self.sweep_curves = [self.sweep_plot.plot(**feat_kw) for _ in range(self.num_curves)]

        pen = et.utils.pg_pen_cycler(1)
        brush = et.utils.pg_brush_cycler(1)
        symbol_kw = dict(symbol="o", symbolSize=1, symbolBrush=brush, symbolPen="k")
        feat_kw = dict(pen=pen, **symbol_kw)
        self.threshold_curves = [self.sweep_plot.plot(**feat_kw) for _ in range(self.num_curves)]

        sweep_plot_legend = pg.LegendItem(offset=(0.0, 0.5))
        sweep_plot_legend.setParentItem(self.sweep_plot)
        sweep_plot_legend.addItem(self.sweep_curves[0], "Sweep")
        sweep_plot_legend.addItem(self.threshold_curves[0], "Threshold")

        font = QFont()
        font.setPixelSize(16)
        self.sweep_text_item = pg.TextItem(
            fill=pg.mkColor(0xFF, 0x7F, 0x0E, 200),
            anchor=(0.5, 0),
            color=pg.mkColor(0xFF, 0xFF, 0xFF, 200),
        )
        self.sweep_text_item.setFont(font)
        self.sweep_text_item.hide()
        self.sweep_plot.addItem(self.sweep_text_item)

        self.sweep_main_peak_line = pg.InfiniteLine(pen=pg.mkPen("k", width=1.5, dash=[2, 8]))
        self.sweep_main_peak_line.hide()
        self.sweep_plot.addItem(self.sweep_main_peak_line)

        # History plot
        self.dist_history_plot = win.addPlot(row=1, col=0)
        self.dist_history_plot.setMenuEnabled(False)
        self.dist_history_plot.showGrid(x=True, y=True)
        self.dist_history_plot.addLegend()
        self.dist_history_plot.setLabel("left", "Estimated distance (m)")
        self.dist_history_plot.addItem(pg.PlotDataItem())
        self.dist_history_plot.setXRange(0, self._DISTANCE_HISTORY_LEN)

        brush = et.utils.pg_brush_cycler(0)
        symbol_kw_main = dict(
            symbol="o", symbolSize=5, symbolBrush=brush, symbolPen=None, pen=None
        )
        feat_kw = dict(**symbol_kw_main)
        self.main_peak_history_curve = self.dist_history_plot.plot(**feat_kw)

        minor_colors = [et.utils.color_cycler(i) for i in range(1, self._MAX_NUM_MINOR_PEAKS)]
        self.minor_peaks_history_curves = [
            self.dist_history_plot.plot(
                **dict(
                    **dict(
                        symbol="o",
                        symbolSize=5,
                        symbolBrush=pg.mkBrush(color),
                        symbolPen=None,
                        pen=None,
                    ),
                )
            )
            for color in minor_colors
        ]

        # History legend
        self.history_plot_legend = pg.LegendItem()
        self.dist_history_plot.addItem(self.history_plot_legend)

        # Smoothing
        self.sweep_smooth_max = et.utils.SmoothMax()
        self.distance_hist_smooth_lim = et.utils.SmoothLimits(tau_decay=0.5)

    def draw_plot_job(self, *, multi_sensor_result: dict[int, DetectorResult]) -> None:
        # Get the first element as the plugin only supports single sensor operation.
        (result,) = list(multi_sensor_result.values())

        assert result.distances is not None
        assert result.strengths is not None

        strengths = result.strengths
        distances = result.distances

        # Update main peak history
        self.main_peak_history = np.roll(self.main_peak_history, shift=-1)
        if len(distances) != 0:
            self.main_peak_history[-1] = distances[0]
        else:
            self.main_peak_history[-1] = np.nan

        # Update minor peaks history
        num_minor_peaks = min(len(distances) - 1, self._MAX_NUM_MINOR_PEAKS)
        new_history = np.full(self._MAX_NUM_MINOR_PEAKS, fill_value=np.nan)
        self.minor_peaks_history = np.roll(self.minor_peaks_history, shift=-1)
        if num_minor_peaks > 0:
            new_history[:num_minor_peaks] = np.array(distances[1 : 1 + num_minor_peaks])
        self.minor_peaks_history[:, -1] = new_history

        # Sweep plot
        max_val_in_plot = 0
        for idx, processor_result in enumerate(result.processor_results):
            assert processor_result.extra_result.used_threshold is not None
            assert processor_result.extra_result.distances_m is not None
            assert processor_result.extra_result.abs_sweep is not None

            abs_sweep = processor_result.extra_result.abs_sweep
            threshold = processor_result.extra_result.used_threshold
            distances_m = processor_result.extra_result.distances_m

            self.sweep_curves[idx].setData(distances_m, abs_sweep)
            self.threshold_curves[idx].setData(distances_m, threshold)

            max_val_in_subsweep = max(max(threshold), max(abs_sweep))
            if max_val_in_plot < max_val_in_subsweep:
                max_val_in_plot = max_val_in_subsweep

        self.sweep_plot.setYRange(0, self.sweep_smooth_max.update(max_val_in_plot))

        if len(distances) != 0:
            text_y_pos = self.sweep_plot.getAxis("left").range[1] * 0.95
            text_x_pos = (
                self.sweep_plot.getAxis("bottom").range[1]
                + self.sweep_plot.getAxis("bottom").range[0]
            ) / 2.0
            self.sweep_text_item.setPos(text_x_pos, text_y_pos)
            self.sweep_text_item.setHtml("Main peak distance: {:.3f} m".format(distances[0]))
            self.sweep_text_item.show()

            self.sweep_main_peak_line.setPos(distances[0])
            self.sweep_main_peak_line.show()
        else:
            self.sweep_text_item.hide()
            self.sweep_main_peak_line.hide()

        # History plot
        self.history_plot_legend.clear()

        if np.any(~np.isnan(self.main_peak_history)):
            self.main_peak_history_curve.setData(self.main_peak_history)
        else:
            self.main_peak_history_curve.setData([0])

        if strengths.size > 0:
            string_to_display = "Main peak strength : {:.1f} dB".format(strengths[0])
            self.history_plot_legend.addItem(self.main_peak_history_curve, string_to_display)

        for sec_peak_idx, curve in enumerate(self.minor_peaks_history_curves):
            if np.any(~np.isnan(self.minor_peaks_history[sec_peak_idx, :])):
                curve.setData(self.minor_peaks_history[sec_peak_idx, :])
            else:
                curve.setData([0])

            if sec_peak_idx + 1 <= num_minor_peaks:
                string_to_display = "Minor peak strength : {:.1f} dB".format(
                    strengths[sec_peak_idx + 1]
                )
                self.history_plot_legend.addItem(curve, string_to_display)

        # Update limits of the history plot
        max_vals = []
        min_vals = []
        if np.any(~np.isnan(self.main_peak_history)):
            max_vals.append(np.nanmax(self.main_peak_history))
            min_vals.append(np.nanmin(self.main_peak_history))

        if np.any(~np.isnan(self.minor_peaks_history)):
            max_vals.append(np.nanmax(self.minor_peaks_history))
            min_vals.append(np.nanmin(self.minor_peaks_history))

        if min_vals:
            lims = self.distance_hist_smooth_lim.update([min(min_vals), max(max_vals)])
        else:
            lims = self.distance_hist_smooth_lim.update([self.start_m, self.end_m])
        lower_lim = max(0.0, lims[0] - self._DISTANCE_HISTORY_SPAN_MARGIN)
        upper_lim = lims[1] + self._DISTANCE_HISTORY_SPAN_MARGIN
        self.dist_history_plot.setYRange(lower_lim, upper_lim)

        # Update position of legend
        y_range = self.dist_history_plot.getAxis("left").range
        x_range = self.dist_history_plot.getAxis("bottom").range
        legend_y_pos = (y_range[1] - y_range[0]) * 0.95 + y_range[0]
        legend_x_pos = (x_range[1]) * 0.01
        self.history_plot_legend.setPos(legend_x_pos, legend_y_pos)


class ViewPlugin(A121ViewPluginBase):
    sensor_config_editors: list[SensorConfigEditor]

    TEXT_MSG_MAP = {
        DetailedStatus.OK: "Ready to start.",
        DetailedStatus.END_LESSER_THAN_START: "'Range end' point must be greater than 'Range "
        + "start'.",
        DetailedStatus.CONTEXT_MISSING: "Run detector calibration.",
        DetailedStatus.CALIBRATION_MISSING: "Run detector calibration.",
        DetailedStatus.CONFIG_MISMATCH: (
            "Current configuration does not match the configuration "
            + "used during detector calibration. Run detector calibration."
        ),
    }

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

        self.calibrate_detector_button = QPushButton(icons.CALIBRATE(), "Calibrate detector")
        self.calibrate_detector_button.clicked.connect(self._on_calibrate_detector)

        self.defaults_button = QPushButton(icons.RESTORE(), "Reset settings and calibrations")
        self.defaults_button.clicked.connect(self._send_defaults_request)

        self.message_box = QLabel(self.sticky_widget)
        self.message_box.setWordWrap(True)

        button_group = GroupBox.grid("Controls", parent=self.sticky_widget)
        button_group.layout().addWidget(self.start_button, 0, 0)
        button_group.layout().addWidget(self.stop_button, 0, 1)
        button_group.layout().addWidget(self.calibrate_detector_button, 1, 0, 1, -1)
        button_group.layout().addWidget(self.defaults_button, 3, 0, 1, -1)
        button_group.layout().addWidget(self.message_box, 4, 0, 1, -1)

        self.misc_error_view = MiscErrorView(self.scrolly_widget)

        sensor_selection_group = GroupBox.vertical("Sensor selection", parent=self.scrolly_widget)
        self.sensor_id_pidget = pidgets.SensorIdPidgetFactory(items=[]).create(
            parent=sensor_selection_group
        )
        self.sensor_id_pidget.sig_update.connect(self._on_sensor_id_update)
        sensor_selection_group.layout().addWidget(self.sensor_id_pidget)

        self.config_editor = AttrsConfigEditor(
            title="Detector parameters",
            factory_mapping=self.get_pidget_mapping(),
            config_type=DetectorConfig,
            extra_presenter=_detector_config_presenter,
            parent=self.scrolly_widget,
        )
        self.config_editor.sig_update.connect(self._on_config_update)

        goto_resource_tab_button = GotoResourceTabButton()
        goto_resource_tab_button.clicked.connect(
            lambda: app_model.sig_resource_tab_input_block_requested.emit(
                self.config_editor.get_data()
            )
        )

        self.sensor_config_editor_tabs = QTabWidget()
        self.sensor_config_editor_tabs.setStyleSheet("QTabWidget::pane { padding: 5px;}")
        self.sensor_config_editors = []
        self.range_labels = ["Close range", "Far range"]

        for label in self.range_labels:
            sensor_config_editor = SensorConfigEditor(
                json_button_operations=JsonButtonOperations.SAVE
            )
            sensor_config_editor.set_read_only(True)
            self.sensor_config_editors.append(sensor_config_editor)
            self.sensor_config_editor_tabs.addTab(sensor_config_editor, label)

        self.collapsible_widget = CollapsibleWidget(
            "Sensor config info", self.sensor_config_editor_tabs, self.scrolly_widget
        )

        sticky_layout = QVBoxLayout()
        sticky_layout.setContentsMargins(0, 0, 0, 0)

        sticky_layout.addWidget(button_group)

        scrolly_layout = QVBoxLayout()
        scrolly_layout.setContentsMargins(0, 0, 0, 0)

        scrolly_layout.addWidget(goto_resource_tab_button)
        scrolly_layout.addWidget(self.misc_error_view)
        scrolly_layout.addWidget(sensor_selection_group)
        scrolly_layout.addWidget(self.config_editor)
        scrolly_layout.addWidget(self.collapsible_widget)

        self.sticky_widget.setLayout(sticky_layout)
        self.scrolly_widget.setLayout(scrolly_layout)

    @classmethod
    def get_pidget_mapping(cls) -> PidgetFactoryMapping:
        return _pidget_mapping.get_pidget_mapping()

    def on_backend_state_update(self, state: Optional[SharedState]) -> None:
        if state is None:
            self.config_editor.set_data(None)
            self.message_box.setText("")
        else:
            (sensor_id,) = state.sensor_ids
            self.sensor_id_pidget.set_data(sensor_id)
            self.config_editor.set_data(state.config)

            self._update_sensor_configs_view(state.config, [sensor_id])

            detector_status = Detector.get_detector_status(
                state.config, state.context, state.sensor_ids
            )

            self.message_box.setText(self.TEXT_MSG_MAP[detector_status.detector_state])

            results = state.config._collect_validation_results()

            not_handled = self.config_editor.handle_validation_results(results)

            not_handled = self.misc_error_view.handle_validation_results(not_handled)

            assert not_handled == []

    def _update_sensor_configs_view(self, config: DetectorConfig, sensor_ids: list[int]) -> None:
        with contextlib.suppress(Exception):
            session_config = detector_config_to_session_config(config, sensor_ids)
            tab_visible = [False, False]
            for group in session_config.groups:
                for _, sensor_config in group.items():
                    index = 0 if sensor_config.subsweeps[0].enable_loopback else 1
                    tab_visible[index] = True
                    sensor_config_editor = self.sensor_config_editors[index]
                    sensor_config_editor.set_data(sensor_config)

            for i, sensor_config_editor in enumerate(self.sensor_config_editors):
                index = self.sensor_config_editor_tabs.indexOf(sensor_config_editor)
                self.sensor_config_editor_tabs.setTabVisible(index, tab_visible[i])

            self.collapsible_widget.widget = self.sensor_config_editor_tabs

    def on_app_model_update(self, app_model: AppModel) -> None:
        self.sensor_id_pidget.set_selectable_sensors(app_model.connected_sensors)

        visual_policies.apply_enabled_policy(
            visual_policies.config_editor_enabled,
            app_model,
            widgets=[self.defaults_button, self.config_editor, self.sensor_id_pidget],
        )
        self.stop_button.setEnabled(visual_policies.stop_button_enabled(app_model))

        state = app_model.backend_plugin_state

        if state is None:
            detector_ready = False
            config_valid = False
        else:
            detector_ready = Detector.get_detector_status(
                state.config, state.context, state.sensor_ids
            ).ready_to_start

            config_valid = self._config_valid(state.config) and self.config_editor.is_ready

        self.calibrate_detector_button.setEnabled(
            visual_policies.start_button_enabled(app_model, extra_condition=config_valid),
        )
        self.start_button.setEnabled(
            visual_policies.start_button_enabled(
                app_model, extra_condition=detector_ready and config_valid
            )
        )

    def _config_valid(self, config: Optional[DetectorConfig]) -> bool:
        if config is None:
            return False

        try:
            config.validate()
        except a121.ValidationError:
            return False
        else:
            return True

    def _on_sensor_id_update(self, sensor_id: int) -> None:
        BackendPlugin.update_sensor_ids.rpc(self.app_model.put_task, sensor_ids=[sensor_id])

    def _on_config_update(self, config: DetectorConfig) -> None:
        BackendPlugin.update_config.rpc(self.app_model.put_task, config=config)

    def _on_calibrate_detector(self) -> None:
        BackendPlugin.calibrate_detector.rpc(self.app_model.put_task)

    def _send_defaults_request(self) -> None:
        BackendPlugin.restore_defaults.rpc(self.app_model.put_task)


def _detector_config_presenter(config: Any, presentation_type: PresentationType) -> Optional[str]:
    if isinstance(config, DetectorConfig) and presentation_type is PresentationType.C_SET_CONFIG:
        max_step_length = 0 if config.max_step_length is None else config.max_step_length

        return f"""
static void set_config(acc_detector_distance_config_t *config, distance_preset_config_t preset)
{{
    // This snippet is generated to be compatible with RSS A121 v1.0.0
    // If there is a version missmatch the snippet might need some modification

    (void)preset;

    acc_detector_distance_config_sensor_set(config, SENSOR_ID);

    acc_detector_distance_config_start_set(config, {config.start_m:.3f}f);
    acc_detector_distance_config_end_set(config, {config.end_m:.3f}f);
    acc_detector_distance_config_max_step_length_set(config, {max_step_length}U);

    acc_detector_distance_config_signal_quality_set(config, {float(config.signal_quality):.3f}f);
    acc_detector_distance_config_max_profile_set(config, ACC_CONFIG_{config.max_profile.name});
    acc_detector_distance_config_peak_sorting_set(config, ACC_DETECTOR_DISTANCE_PEAK_SORTING_{config.peaksorting_method.name});
    acc_detector_distance_config_reflector_shape_set(config, ACC_DETECTOR_DISTANCE_REFLECTOR_SHAPE_{config.reflector_shape.name});

    acc_detector_distance_config_threshold_method_set(config, ACC_DETECTOR_DISTANCE_THRESHOLD_METHOD_{config.threshold_method.name});
    acc_detector_distance_config_num_frames_recorded_threshold_set(config, {config.num_frames_in_recorded_threshold}U);
    acc_detector_distance_config_fixed_threshold_value_set(config, {config.fixed_threshold_value:.3f}f);
    acc_detector_distance_config_threshold_sensitivity_set(config, {config.threshold_sensitivity:.3f}f);

    acc_detector_distance_config_close_range_leakage_cancellation_set(config, {str(config.close_range_leakage_cancellation).lower()});
}}
"""

    return None


class PluginSpec(PluginSpecBase):
    def create_backend_plugin(
        self, callback: Callable[[Message], None], key: str
    ) -> BackendPlugin:
        return BackendPlugin(callback, generation=self.generation, key=key)

    def create_view_plugin(self, app_model: AppModel) -> ViewPlugin:
        return ViewPlugin(app_model=app_model)

    def create_plot_plugin(self, app_model: AppModel) -> PlotPlugin:
        return PlotPlugin(app_model=app_model)


DISTANCE_DETECTOR_PLUGIN = PluginSpec(
    generation=PluginGeneration.A121,
    key="distance_detector",
    title="Distance detector",
    docs_link="https://docs.acconeer.com/en/latest/detectors/a121/distance_detector.html",
    description="Easily measure distance to objects.",
    family=PluginFamily.DETECTOR,
    presets=[
        PluginPresetBase(name="Balanced", preset_id=PluginPresetId.BALANCED),
        PluginPresetBase(name="High accuracy", preset_id=PluginPresetId.HIGH_ACCURACY),
    ],
    default_preset_id=PluginPresetId.BALANCED,
)
