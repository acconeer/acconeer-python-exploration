# Copyright (c) Acconeer AB, 2023-2025
# All rights reserved

from __future__ import annotations

import logging
import math
import time
from enum import Enum, auto
from typing import Any, Callable, Mapping, Optional

import attrs
import h5py
import numpy as np

from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121, opser
from acconeer.exptool._core.docstrings import get_attribute_docstring
from acconeer.exptool.a121._h5_utils import _create_h5_string_dataset
from acconeer.exptool.a121.algo._plugins import (
    A121BackendPluginBase,
    A121ViewPluginBase,
)
from acconeer.exptool.a121.algo.distance._detector import DetailedStatus, Detector
from acconeer.exptool.a121.algo.distance._detector_plugin import ViewPlugin as DistanceViewPlugin
from acconeer.exptool.a121.algo.tank_level._configs import (
    get_large_config,
    get_medium_config,
    get_small_config,
)
from acconeer.exptool.a121.algo.tank_level._processor import ProcessorLevelStatus
from acconeer.exptool.a121.algo.tank_level._ref_app import (
    RefApp,
    RefAppConfig,
    RefAppContext,
    RefAppResult,
    _load_algo_data,
    ref_app_context_timeline,
)
from acconeer.exptool.app.new import (
    AppModel,
    BackendLogger,
    GeneralMessage,
    GroupBox,
    HandledException,
    Message,
    PgPlotPlugin,
    PluginFamily,
    PluginGeneration,
    PluginPresetBase,
    PluginSpecBase,
    PluginState,
    PluginStateMessage,
    backend,
    icons,
    is_task,
    visual_policies,
)
from acconeer.exptool.app.new.ui.components import (
    AttrsConfigEditor,
    PidgetFactoryMapping,
    PidgetGroupFactoryMapping,
    PresentationType,
    pidgets,
)
from acconeer.exptool.app.new.ui.components.pidgets.hooks import (
    disable_if,
    parameter_is,
)


log = logging.getLogger(__name__)


NO_DETECTION_TIMEOUT = 50
TIME_HISTORY_S = 30
UPDATE_RATE_EXP_FILTER = 0.1


@attrs.mutable(kw_only=True)
class SharedState:
    sensor_id: int = attrs.field(default=1)
    config: RefAppConfig = attrs.field(factory=RefAppConfig)
    context: RefAppContext = attrs.field(factory=RefAppContext)


class PluginPresetId(Enum):
    SMALL = auto()
    MEDIUM = auto()
    LARGE = auto()


@attrs.mutable(kw_only=True)
class TankLevelPreset:
    config: RefAppConfig = attrs.field()


@attrs.frozen(kw_only=True)
class SetupMessage(GeneralMessage):
    config: RefAppConfig
    num_curves: int
    name: str = attrs.field(default="setup", init=False)
    recipient: backend.RecipientLiteral = attrs.field(default="plot_plugin", init=False)


class BackendPlugin(A121BackendPluginBase[SharedState]):
    PLUGIN_PRESETS: Mapping[int, TankLevelPreset] = {
        PluginPresetId.SMALL.value: TankLevelPreset(
            config=get_small_config(),
        ),
        PluginPresetId.MEDIUM.value: TankLevelPreset(
            config=get_medium_config(),
        ),
        PluginPresetId.LARGE.value: TankLevelPreset(
            config=get_large_config(),
        ),
    }

    def __init__(
        self, callback: Callable[[Message], None], generation: PluginGeneration, key: str
    ) -> None:
        super().__init__(callback=callback, generation=generation, key=key, use_app_client=False)

        self._recorder = None
        self._ref_app_instance: Optional[RefApp] = None
        self._log = BackendLogger.getLogger(__name__)
        self._last_get_next_time_s: Optional[float] = None
        self._actual_update_rate_hz = 0.0
        self._frame_count = 0

        self.restore_defaults()

    def _load_from_cache(self, file: h5py.File) -> None:
        self.shared_state.config = RefAppConfig.from_json(file["config"][()])
        self.shared_state.context = ref_app_context_timeline.migrate(file["context"])

    @is_task
    def restore_defaults(self) -> None:
        self.shared_state = SharedState(config=get_small_config())
        self.broadcast()

    def _sync_sensor_ids(self) -> None:
        if self.client is not None:
            sensor_ids = self.client.server_info.connected_sensors

            if len(sensor_ids) > 0 and self.shared_state.sensor_id not in sensor_ids:
                self.shared_state.sensor_id = sensor_ids[0]

    @is_task
    def update_config(self, *, config: RefAppConfig) -> None:
        self.shared_state.config = config
        self.broadcast()

    @is_task
    def update_sensor_id(self, *, sensor_id: int) -> None:
        self.shared_state.sensor_id = sensor_id
        self.broadcast()

    @is_task
    def set_preset(self, preset_id: int) -> None:
        preset_config = self.PLUGIN_PRESETS[preset_id]
        self.shared_state.config = preset_config.config
        self.broadcast()

    def save_to_cache(self, file: h5py.File) -> None:
        _create_h5_string_dataset(file, "config", self.shared_state.config.to_json())
        context_group = file.create_group("context")
        opser.serialize(self.shared_state.context, context_group)

    def load_from_record_setup(self, *, record: a121.H5Record) -> None:
        algo_group = record.get_algo_group(self.key)
        sensor_id, config, context = _load_algo_data(algo_group)
        self.shared_state.config = config
        self.shared_state.context = context
        self.shared_state.sensor_id = sensor_id

    def _start_session(self, recorder: Optional[a121.H5Recorder]) -> None:
        assert self.client

        self._ref_app_instance = RefApp(
            client=self.client,
            sensor_id=self.shared_state.sensor_id,
            config=self.shared_state.config,
            context=self.shared_state.context,
        )

        self._ref_app_instance.start(recorder)

        self.callback(
            SetupMessage(
                config=self.shared_state.config,
                num_curves=len(self._ref_app_instance._detector.processor_specs),
            )
        )

    def end_session(self) -> None:
        if self._ref_app_instance is None:
            raise RuntimeError

        if self._recorder is not None:
            self._recorder.close()

        self._ref_app_instance.stop()

        self._clear_rate_stats()

    def get_next(self) -> None:
        assert self.client is not None
        if self._ref_app_instance is None:
            raise RuntimeError

        sleep_time = self._sleep_until_next_frame()

        self._actual_update_rate_hz = self._iteratively_estimate_update_rate(
            last_get_next_time_s=self._last_get_next_time_s,
            current_estimated_update_rate=self._actual_update_rate_hz,
        )

        self._last_get_next_time_s = time.perf_counter()
        result = self._ref_app_instance.get_next()

        # Report frame count and update-rate to GUI.
        # usually done in ApplicationClient but because of erratic behavior
        # when distance detector is re-calibrated, it has to be done by the
        # ref app plugin instead.
        self._update_rate_stats(sleep_time=sleep_time, result=result)

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
            self._ref_app_instance = RefApp(
                client=self.client,
                sensor_id=self.shared_state.sensor_id,
                config=self.shared_state.config,
                context=None,
            )
            self._ref_app_instance.calibrate()
        except Exception as exc:
            msg = "Failed to calibrate detector"
            raise HandledException(msg) from exc
        finally:
            self.callback(PluginStateMessage(state=PluginState.LOADED_IDLE))

        self.shared_state.context = self._ref_app_instance._detector.context
        self.broadcast()

    def _sleep_until_next_frame(self) -> Optional[float]:
        if self._ref_app_instance is None:
            raise RuntimeError

        if self._ref_app_instance.config.update_rate is None:
            return None

        if self._last_get_next_time_s is None:
            return None

        sleep_time = (
            self._last_get_next_time_s
            + 1 / self._ref_app_instance.config.update_rate
            - time.perf_counter()
        )

        if sleep_time > 0:
            time.sleep(sleep_time)

        return sleep_time

    @staticmethod
    def _iteratively_estimate_update_rate(
        last_get_next_time_s: Optional[float], current_estimated_update_rate: float
    ) -> float:
        if last_get_next_time_s is None:
            return 0.0

        actual_update_rate_hz = UPDATE_RATE_EXP_FILTER * current_estimated_update_rate + (
            1 - UPDATE_RATE_EXP_FILTER
        ) / (time.perf_counter() - last_get_next_time_s)

        return actual_update_rate_hz

    def _update_rate_stats(self, sleep_time: Optional[float], result: RefAppResult) -> None:
        if sleep_time is not None:
            if sleep_time > 0:  # had time to sleep -> No rate warning
                stats = backend._RateStats(self._actual_update_rate_hz, False, math.nan, False)
                self.callback(GeneralMessage(name="rate_stats", data=stats))
            else:  # no time to sleep -> rate warning
                stats = backend._RateStats(self._actual_update_rate_hz, True, math.nan, False)
                self.callback(GeneralMessage(name="rate_stats", data=stats))
        else:  # Run as fast as possible -> no rate warning
            stats = backend._RateStats(self._actual_update_rate_hz, False, math.nan, False)
            self.callback(GeneralMessage(name="rate_stats", data=stats))

        for value in result.extra_result.detector_result.values():
            self._frame_count += len(
                value.service_extended_result
            )  # count frames in extended result
        self.callback(backend.PlotMessage(result=result))
        self.callback(GeneralMessage(name="frame_count", data=self._frame_count))

    def _clear_rate_stats(self) -> None:
        self._last_get_next_time_s = None
        self._actual_update_rate_hz = 0.0
        self._frame_count = 0
        self.callback(GeneralMessage(name="rate_stats", data=None))
        self.callback(GeneralMessage(name="frame_count", data=None))


class PlotPlugin(PgPlotPlugin):
    STATUS_MSG_MAP = {
        ProcessorLevelStatus.IN_RANGE: "In range",
        ProcessorLevelStatus.NO_DETECTION: "Not available",
        ProcessorLevelStatus.OVERFLOW: "Warning: Overflow",
        ProcessorLevelStatus.OUT_OF_RANGE: "Out of range",
    }

    def __init__(self, app_model: AppModel) -> None:
        super().__init__(app_model=app_model)

        self.counter = 0
        self.bar_loc = 0

        self._plot_job: Optional[RefAppResult] = None
        self._is_setup = False

    def handle_message(self, message: backend.GeneralMessage) -> None:
        if isinstance(message, backend.PlotMessage):
            self._plot_job = message.result
        elif isinstance(message, SetupMessage):
            self.setup(message.config, message.num_curves)
            self._is_setup = True
        else:
            log.warn(f"{self.__class__.__name__} got an unsupported command: {message.name!r}.")

    def draw(self) -> None:
        if not self._is_setup or self._plot_job is None:
            return

        try:
            self.draw_plot_job(result=self._plot_job)
        finally:
            self._plot_job = None

    def setup(
        self,
        config: RefAppConfig,
        num_curves: int,
    ) -> None:
        self.plot_layout.clear()

        self.num_curves = num_curves
        self.start_m = config.start_m
        self.end_m = config.end_m

        win = self.plot_layout

        # Sweep plot
        self.sweep_plot = win.addPlot(row=1, col=0, colspan=3)
        self.sweep_plot.setMenuEnabled(False)
        self.sweep_plot.showGrid(x=True, y=True)
        self.sweep_plot.addLegend()
        self.sweep_plot.setLabel("left", "Amplitude")
        self.sweep_plot.setLabel("bottom", "Distance (m)")
        self.sweep_plot.addItem(pg.PlotDataItem())

        self.vertical_line_start = pg.InfiniteLine(
            pen=et.utils.pg_pen_cycler(2),
            label="Tank start",
            labelOpts={
                "position": 0.5,
                "color": (0, 100, 0),
                "fill": (200, 200, 200, 50),
                "movable": True,
            },
        )
        self.sweep_plot.addItem(self.vertical_line_start)
        self.vertical_line_end = pg.InfiniteLine(
            pen=et.utils.pg_pen_cycler(2),
            label="Tank end",
            labelOpts={
                "position": 0.5,
                "color": (0, 100, 0),
                "fill": (200, 200, 200, 50),
                "movable": True,
            },
        )
        self.sweep_plot.addItem(self.vertical_line_end)

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

        # Level history plot
        self.level_history_plot = win.addPlot(row=0, col=1, colspan=2)
        self.level_history_plot.setMenuEnabled(False)
        self.level_history_plot.showGrid(x=True, y=True)
        self.level_history_plot.addLegend()
        self.level_history_plot.setLabel("left", "Estimated level (cm)")
        self.level_history_plot.setLabel("bottom", "Time (s)")
        self.level_history_plot.addItem(pg.PlotDataItem())

        pen = et.utils.pg_pen_cycler(0)
        brush = et.utils.pg_brush_cycler(0)
        symbol_kw = dict(symbol="o", symbolSize=5, symbolBrush=brush, symbolPen="k")
        feat_kw = dict(pen=pen, **symbol_kw)
        self.level_history_curve = self.level_history_plot.plot(**feat_kw)

        self.sweep_smooth_max = et.utils.SmoothMax()
        self.distance_hist_smooth_lim = et.utils.SmoothLimits()

        # Rect plot
        self.num_rects = 15
        self.rect_plot = pg.PlotItem()
        self.rect_plot.setAspectLocked()
        self.rect_plot.hideAxis("left")
        self.rect_plot.hideAxis("bottom")
        self.rects = []

        pen = pg.mkPen(None)
        rect_width = self.num_rects / 2.0
        for r in np.arange(self.num_rects) + 1:
            rect = pg.QtWidgets.QGraphicsRectItem(0, r, rect_width, 1)
            rect.setPen(pen)
            self.rect_plot.addItem(rect)
            self.rects.append(rect)

        self.plot_layout.addItem(self.rect_plot, row=0, col=0)

        # text items
        self.level_html_format = (
            '<div style="text-align: center">'
            '<span style="color: #FFFFFF;font-size:12pt;">'
            "{}</span></div>"
        )

        self.level_text_item = pg.TextItem(
            fill=pg.mkColor(0x1F, 0x77, 0xB4, 180),
            anchor=(0.5, 0),
        )

        self.rect_plot.addItem(self.level_text_item)
        self.level_text_item.hide()

    def draw_plot_job(
        self,
        *,
        result: RefAppResult,
    ) -> None:
        # Get the first element as the plugin only supports single sensor operation.
        (detector_result,) = list(result.extra_result.detector_result.values())
        assert detector_result.distances is not None

        time_and_level_dict = (
            result.extra_result.processor_extra_result.level_and_time_for_plotting
        )

        # clear sweep plots
        for idx, _ in enumerate(self.sweep_curves):
            self.sweep_curves[idx].clear()
            self.threshold_curves[idx].clear()
        # update sweep plot
        max_val_in_plot = 0
        for idx, processor_result in enumerate(detector_result.processor_results):
            assert processor_result.extra_result.used_threshold is not None
            assert processor_result.extra_result.distances_m is not None
            assert processor_result.extra_result.abs_sweep is not None

            self.sweep_curves[idx].setData(
                processor_result.extra_result.distances_m, processor_result.extra_result.abs_sweep
            )

            self.threshold_curves[idx].setData(
                processor_result.extra_result.distances_m,
                processor_result.extra_result.used_threshold,
            )

            max_val_in_subsweep = max(
                max(processor_result.extra_result.used_threshold),
                max(processor_result.extra_result.abs_sweep),
            )

            max_val_in_plot = max(max_val_in_plot, max_val_in_subsweep)

        self.sweep_plot.setYRange(0, self.sweep_smooth_max.update(max_val_in_plot))
        self.vertical_line_start.setValue(self.start_m)
        self.vertical_line_end.setValue(self.end_m)
        self.vertical_line_start.show()
        self.vertical_line_end.show()

        # update level history plot
        if any(~np.isnan(time_and_level_dict["level"])):
            self.level_history_curve.setData(
                time_and_level_dict["time"], time_and_level_dict["level"] * 100
            )
            self.level_history_plot.setXRange(-TIME_HISTORY_S + 1, 0)
            self.level_history_plot.setYRange(0, (self.end_m - self.start_m + 0.01) * 100)

        # update level plot
        if (
            result.level is not None
            and result.peak_detected is not None
            and result.peak_status is not None
        ):
            current_level = result.level
            peak_detected = result.peak_detected
            peak_status = result.peak_status

            # Show the percentage level plot if the plot width is greater than 600 pixels,
            # otherwise display the level as text.
            if self.plot_layout.width() >= 600:
                level_text = self.STATUS_MSG_MAP[peak_status]
                if peak_status == ProcessorLevelStatus.OVERFLOW:
                    for rect in self.rects:
                        rect.setBrush(et.utils.pg_brush_cycler(0))
                elif peak_detected and (peak_status == ProcessorLevelStatus.IN_RANGE):
                    self.bar_loc = round(
                        current_level / (self.end_m - self.start_m) * self.num_rects
                    )
                    for rect in self.rects[: self.bar_loc]:
                        rect.setBrush(et.utils.pg_brush_cycler(0))

                    for rect in self.rects[self.bar_loc :]:
                        rect.setBrush(et.utils.pg_brush_cycler(1))

                    level_text = "Level: {:.1f} cm, {:.0f} %".format(
                        current_level * 100,
                        current_level / (self.end_m - self.start_m) * 100,
                    )
                    self.counter = 0
                elif peak_detected and (peak_status == ProcessorLevelStatus.OUT_OF_RANGE):
                    for rect in self.rects:
                        rect.setBrush(et.utils.pg_brush_cycler(1))
                elif (not peak_detected) and (self.counter <= NO_DETECTION_TIMEOUT):
                    for rect in self.rects[: self.bar_loc]:
                        rect.setBrush(et.utils.pg_brush_cycler(0))

                    for rect in self.rects[self.bar_loc :]:
                        rect.setBrush(et.utils.pg_brush_cycler(1))

                    self.counter += 1
                else:
                    for rect in self.rects:
                        rect.setBrush(et.utils.pg_brush_cycler(1))
                        self.bar_loc = 0
                for rect in self.rects:
                    rect.setVisible(True)

                level_html = self.level_html_format.format(level_text)
                self.level_text_item.setHtml(level_html)
                self.level_text_item.setPos(self.num_rects / 4.0, self.num_rects + 4.0)
                self.level_text_item.show()
            else:
                level_text = self.STATUS_MSG_MAP[peak_status]
                if peak_detected and (peak_status == ProcessorLevelStatus.IN_RANGE):
                    level_text = "Level: {:.1f} cm, {:.0f} %".format(
                        current_level * 100,
                        current_level / (self.end_m - self.start_m) * 100,
                    )
                    self.counter = 0
                level_html = self.level_html_format.format(level_text)
                self.level_text_item.setHtml(level_html)
                self.level_text_item.setPos(self.num_rects / 4.0, self.num_rects + 4.0)
                self.level_text_item.show()
                for rect in self.rects:
                    rect.setVisible(False)


class ViewPlugin(A121ViewPluginBase):
    TEXT_MSG_MAP = {
        DetailedStatus.OK: "Ready to start.",
        DetailedStatus.CONTEXT_MISSING: "Run detector calibration.",
        DetailedStatus.CALIBRATION_MISSING: "Run detector calibration.",
        DetailedStatus.CONFIG_MISMATCH: (
            "Current configuration does not match the configuration "
            + "used during detector calibration. Run detector calibration."
        ),
    }

    def __init__(self, app_model: AppModel) -> None:
        super().__init__(app_model=app_model)
        self.app_model = app_model
        self._log = logging.getLogger(__name__)

        sticky_layout = QVBoxLayout()
        sticky_layout.setContentsMargins(0, 0, 0, 0)
        scrolly_layout = QVBoxLayout()
        scrolly_layout.setContentsMargins(0, 0, 0, 0)

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

        sticky_layout.addWidget(button_group)

        sensor_selection_group = GroupBox.vertical("Sensor selection", parent=self.scrolly_widget)
        self.sensor_id_pidget = pidgets.SensorIdPidgetFactory(items=[]).create(
            parent=sensor_selection_group
        )
        self.sensor_id_pidget.sig_update.connect(self._on_sensor_id_update)
        sensor_selection_group.layout().addWidget(self.sensor_id_pidget)
        scrolly_layout.addWidget(sensor_selection_group)

        self.tank_level_config_editor = AttrsConfigEditor(
            title="Tank level indicator parameters",
            factory_mapping=self._get_processor_pidget_mapping(),
            config_type=RefAppConfig,
            extra_presenter=_set_config_presenter,
            parent=self.scrolly_widget,
        )
        self.tank_level_config_editor.sig_update.connect(self._on_config_update)
        scrolly_layout.addWidget(self.tank_level_config_editor)

        self.config_editor = AttrsConfigEditor(
            title="Detector parameters",
            factory_mapping=self._get_detector_pidget_mapping(),
            config_type=RefAppConfig,
            save_load_buttons=False,
            parent=self.scrolly_widget,
        )
        self.config_editor.sig_update.connect(self._on_config_update)
        scrolly_layout.addWidget(self.config_editor)

        self.sticky_widget.setLayout(sticky_layout)
        self.scrolly_widget.setLayout(scrolly_layout)

    @classmethod
    def _get_processor_pidget_mapping(cls) -> PidgetGroupFactoryMapping:
        partial_range_params = {
            "partial_tracking_range_m": pidgets.FloatPidgetFactory(
                name_label_text="Partial tracking range:",
                name_label_tooltip=get_attribute_docstring(
                    RefAppConfig, "partial_tracking_range_m"
                ),
                suffix=" m",
                decimals=3,
                limits=(0, 23),
            ),
        }
        return {
            pidgets.FlatPidgetGroup(): {
                "median_filter_length": pidgets.IntPidgetFactory(
                    name_label_text="Median filter length:",
                    name_label_tooltip=get_attribute_docstring(
                        RefAppConfig, "median_filter_length"
                    ),
                    limits=(1, 10),
                ),
                "num_medians_to_average": pidgets.IntPidgetFactory(
                    name_label_text="Num measurements averaged:",
                    name_label_tooltip=get_attribute_docstring(
                        RefAppConfig, "num_medians_to_average"
                    ),
                    limits=(1, 10),
                ),
                "start_m": pidgets.FloatPidgetFactory(
                    name_label_text="Tank start:",
                    name_label_tooltip=get_attribute_docstring(RefAppConfig, "start_m"),
                    suffix=" m",
                    decimals=3,
                    limits=(0.03, 23),
                ),
                "end_m": pidgets.FloatPidgetFactory(
                    name_label_text="Tank end:",
                    name_label_tooltip=get_attribute_docstring(RefAppConfig, "end_m"),
                    suffix=" m",
                    decimals=3,
                    limits=(0.05, 23),
                ),
                "level_tracking_active": pidgets.CheckboxPidgetFactory(
                    name_label_text="Level tracking active",
                    name_label_tooltip=get_attribute_docstring(
                        RefAppConfig, "level_tracking_active"
                    ),
                ),
            },
            pidgets.FlatPidgetGroup(
                hooks=disable_if(parameter_is("level_tracking_active", False)),
            ): partial_range_params,
            pidgets.FlatPidgetGroup(): {
                "update_rate": pidgets.OptionalFloatPidgetFactory(
                    name_label_tooltip=get_attribute_docstring(RefAppConfig, "update_rate"),
                    name_label_text="Update rate:",
                    checkbox_label_text="Limit",
                    suffix=" Hz",
                    limits=(0.5, None),
                    init_set_value=1,
                ),
            },
        }

    @classmethod
    def _get_detector_pidget_mapping(cls) -> PidgetFactoryMapping:
        COMMON_PIDGETS = {
            "max_profile",
            "reflector_shape",
            "peaksorting_method",
            "threshold_method",
            "fixed_threshold_value",
            "fixed_strength_threshold_value",
            "num_frames_in_recorded_threshold",
            "threshold_sensitivity",
            "signal_quality",
            "close_range_leakage_cancellation",
        }

        return {
            "max_step_length": pidgets.OptionalIntPidgetFactory(
                name_label_text="Max step length:",
                checkbox_label_text="Set",
                limits=(1, None),
                init_set_value=1,
            ),
            **{
                aspect: factory
                for aspect, factory in DistanceViewPlugin.get_pidget_mapping().items()
                if aspect in COMMON_PIDGETS
            },
        }

    def on_backend_state_update(self, state: Optional[SharedState]) -> None:
        if state is None:
            self.config_editor.set_data(None)
            self.tank_level_config_editor.set_data(None)
            self.message_box.setText("")
        else:
            self.sensor_id_pidget.set_data(state.sensor_id)
            self.config_editor.set_data(state.config)
            self.tank_level_config_editor.set_data(state.config)

            detector_status = Detector.get_detector_status(
                state.config.to_detector_config(), state.context, [state.sensor_id]
            )

            self.message_box.setText(self.TEXT_MSG_MAP[detector_status.detector_state])

            results = state.config._collect_validation_results()

            not_handled = self.tank_level_config_editor.handle_validation_results(results)
            not_handled = self.config_editor.handle_validation_results(not_handled)

            assert not_handled == []

    def on_app_model_update(self, app_model: AppModel) -> None:
        self.sensor_id_pidget.set_selectable_sensors(app_model.connected_sensors)

        visual_policies.apply_enabled_policy(
            visual_policies.config_editor_enabled,
            app_model,
            widgets=[
                self.defaults_button,
                self.config_editor,
                self.tank_level_config_editor,
                self.sensor_id_pidget,
            ],
        )

        self.stop_button.setEnabled(visual_policies.stop_button_enabled(app_model))

        state = app_model.backend_plugin_state

        if state is None:
            detector_ready = False
            config_valid = False
        else:
            detector_ready = Detector.get_detector_status(
                state.config.to_detector_config(), state.context, [state.sensor_id]
            ).ready_to_start

            config_valid = (
                self._config_valid(state.config)
                and self.config_editor.is_ready
                and self.tank_level_config_editor.is_ready
            )

        self.calibrate_detector_button.setEnabled(
            visual_policies.start_button_enabled(app_model, extra_condition=config_valid)
        )
        self.start_button.setEnabled(
            visual_policies.start_button_enabled(
                app_model, extra_condition=detector_ready and config_valid
            )
        )

    def _config_valid(self, config: Optional[RefAppConfig]) -> bool:
        if config is None:
            return False

        try:
            config.validate()
        except a121.ValidationError:
            return False
        else:
            return True

    def _on_sensor_id_update(self, sensor_id: int) -> None:
        BackendPlugin.update_sensor_id.rpc(self.app_model.put_task, sensor_id=sensor_id)

    def _on_config_update(self, config: RefAppConfig) -> None:
        BackendPlugin.update_config.rpc(self.app_model.put_task, config=config)

    # TODO: move to detector base (?)
    def _send_start_request(self) -> None:
        BackendPlugin.start_session.rpc(
            self.app_model.put_task, with_recorder=self.app_model.recording_enabled
        )

    # TODO: move to detector base (?)
    def _send_stop_request(self) -> None:
        BackendPlugin.stop_session.rpc(self.app_model.put_task)

    def _on_calibrate_detector(self) -> None:
        BackendPlugin.calibrate_detector.rpc(self.app_model.put_task)

    def _send_defaults_request(self) -> None:
        BackendPlugin.restore_defaults.rpc(self.app_model.put_task)


def _set_config_presenter(instance: Any, presentation_type: PresentationType) -> Optional[str]:
    if isinstance(instance, RefAppConfig) and presentation_type is PresentationType.C_SET_CONFIG:
        config: RefAppConfig = instance
        distance_config = config.to_detector_config()

        return f"""
static void set_config(acc_ref_app_tank_level_config_t *config, tank_level_preset_config_t preset)
{{
    // This snippet is generated to be compatible with RSS A121 v1.0.0
    // If there is a version missmatch the snippet might need some modification

    (void)preset;

    config->tank_range_start_m     = {config.start_m:.3f}f;
    config->tank_range_end_m       = {config.end_m:.3f}f;
    config->median_filter_length   = {config.median_filter_length}U;
    config->num_medians_to_average = {config.num_medians_to_average}U;

    acc_detector_distance_config_start_set(config->distance_config, {distance_config.start_m:.3f}f);
    acc_detector_distance_config_end_set(config->distance_config, {distance_config.end_m:.3f}f);
    acc_detector_distance_config_max_step_length_set(config->distance_config, {distance_config.max_step_length or 0}U);
    acc_detector_distance_config_max_profile_set(config->distance_config, ACC_CONFIG_{distance_config.max_profile.name});
    acc_detector_distance_config_num_frames_recorded_threshold_set(config->distance_config, {distance_config.num_frames_in_recorded_threshold}U);
    acc_detector_distance_config_peak_sorting_set(config->distance_config, ACC_DETECTOR_DISTANCE_PEAK_SORTING_{distance_config.peaksorting_method.name});
    acc_detector_distance_config_reflector_shape_set(config->distance_config, ACC_DETECTOR_DISTANCE_REFLECTOR_SHAPE_{distance_config.reflector_shape.name});
    acc_detector_distance_config_threshold_sensitivity_set(config->distance_config, {distance_config.threshold_sensitivity:.3f}f);
    acc_detector_distance_config_signal_quality_set(config->distance_config, {distance_config.signal_quality:.3f}f);
    acc_detector_distance_config_close_range_leakage_cancellation_set(config->distance_config, {str(distance_config.close_range_leakage_cancellation).lower()});
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


TANK_LEVEL_PLUGIN = PluginSpec(
    generation=PluginGeneration.A121,
    key="tank_level",
    title="Tank level",
    docs_link="https://docs.acconeer.com/en/latest/ref_apps/a121/tank_level.html",
    description="Measure liquid levels in tanks",
    family=PluginFamily.REF_APP,
    presets=[
        PluginPresetBase(name="Small", preset_id=PluginPresetId.SMALL),
        PluginPresetBase(name="Medium", preset_id=PluginPresetId.MEDIUM),
        PluginPresetBase(name="Large", preset_id=PluginPresetId.LARGE),
    ],
    default_preset_id=PluginPresetId.SMALL,
)
