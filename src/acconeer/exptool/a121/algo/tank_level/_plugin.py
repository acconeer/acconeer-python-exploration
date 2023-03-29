# Copyright (c) Acconeer AB, 2023
# All rights reserved

from __future__ import annotations

import logging
from enum import Enum, auto
from typing import Callable, Mapping, Optional

import attrs
import h5py
import numpy as np
import qtawesome as qta

from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121._h5_utils import _create_h5_string_dataset
from acconeer.exptool.a121.algo._plugins import (
    DetectorBackendPluginBase,
    DetectorPlotPluginBase,
    DetectorViewPluginBase,
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
)
from acconeer.exptool.app.new import (
    BUTTON_ICON_COLOR,
    AppModel,
    BackendLogger,
    GeneralMessage,
    HandledException,
    Message,
    PluginFamily,
    PluginGeneration,
    PluginPresetBase,
    PluginSpecBase,
    PluginState,
    PluginStateMessage,
    VerticalGroupBox,
    is_task,
)
from acconeer.exptool.app.new.ui.plugin_components import (
    AttrsConfigEditor,
    GridGroupBox,
    PidgetFactoryMapping,
    pidgets,
)


NO_DETECTION_TIMEOUT = 50


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


class BackendPlugin(DetectorBackendPluginBase[SharedState]):

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
        super().__init__(callback=callback, generation=generation, key=key)

        self._recorder = None
        self._ref_app_instance: Optional[RefApp] = None
        self._log = BackendLogger.getLogger(__name__)

        self.restore_defaults()

    @is_task
    def _load_from_cache(self, file: h5py.File) -> None:
        self.shared_state.config = RefAppConfig.from_json(file["config"][()])
        self.shared_state.context = RefAppContext.from_h5(file["context"])

    @is_task
    def restore_defaults(self) -> None:
        self.shared_state = SharedState(config=get_small_config())
        self.broadcast(sync=True)

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
        self.broadcast(sync=True)

    def save_to_cache(self, file: h5py.File) -> None:
        _create_h5_string_dataset(file, "config", self.shared_state.config.to_json())
        context_group = file.create_group("context")
        self.shared_state.context.to_h5(context_group)

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
            GeneralMessage(
                name="setup",
                kwargs={
                    "config": self.shared_state.config,
                    "num_curves": len(self._ref_app_instance._detector.processor_specs),
                },
                recipient="plot_plugin",
            )
        )

    def end_session(self) -> None:
        if self._ref_app_instance is None:
            raise RuntimeError
        self._ref_app_instance.stop()

    def get_next(self) -> None:
        assert self.client is not None
        if self._ref_app_instance is None:
            raise RuntimeError
        result = self._ref_app_instance.get_next()

        self.callback(GeneralMessage(name="plot", data=result, recipient="plot_plugin"))

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
            raise HandledException("Failed to calibrate detector") from exc
        finally:
            self.callback(PluginStateMessage(state=PluginState.LOADED_IDLE))

        self.shared_state.context = self._ref_app_instance._detector.context
        self.broadcast()


class PlotPlugin(DetectorPlotPluginBase):

    STATUS_MSG_MAP = {
        ProcessorLevelStatus.IN_RANGE: "In range",
        ProcessorLevelStatus.NO_DETECTION: "Not available",
        ProcessorLevelStatus.OVERFLOW: "Warning: Overflow",
        ProcessorLevelStatus.OUT_OF_RANGE: "Out of range",
    }

    def __init__(self, *, plot_layout: pg.GraphicsLayout, app_model: AppModel) -> None:
        super().__init__(plot_layout=plot_layout, app_model=app_model)

        self.counter = 0
        self.bar_loc = 0

    def setup_from_message(self, message: GeneralMessage) -> None:
        assert message.kwargs is not None
        self.setup(**message.kwargs)

    def update_from_message(self, message: GeneralMessage) -> None:
        assert isinstance(message.data, RefAppResult)
        self.update(message.data)

    def setup(
        self,
        config: RefAppConfig,
        num_curves: int,
    ) -> None:

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

    def update(
        self,
        result: RefAppResult,
    ) -> None:
        # Get the first element as the plugin only supports single sensor operation.
        (detector_result,) = list(result.extra_result.detector_result.values())
        assert detector_result.distances is not None

        time_and_level_dict = (
            result.extra_result.processor_extra_result.level_and_time_for_plotting
        )

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

        if (
            result.level is not None
            and result.peak_detected is not None
            and result.peak_status is not None
        ):
            current_level = result.level
            peak_detected = result.peak_detected
            peak_status = result.peak_status
            # update level history plot
            if any(~np.isnan(time_and_level_dict["level"])):
                self.level_history_curve.setData(
                    time_and_level_dict["time"], time_and_level_dict["level"] * 100
                )
                self.level_history_plot.setXRange(-30 + 1, 0)
                self.level_history_plot.setYRange(0, (self.end_m - self.start_m + 0.01) * 100)

            # update level plot
            level_text = self.STATUS_MSG_MAP[peak_status]
            if peak_status == ProcessorLevelStatus.OVERFLOW:
                for rect in self.rects:
                    rect.setBrush(et.utils.pg_brush_cycler(0))
            elif peak_detected and (peak_status == ProcessorLevelStatus.IN_RANGE):
                self.bar_loc = round(current_level / (self.end_m - self.start_m) * self.num_rects)
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
            elif ~peak_detected and (self.counter <= NO_DETECTION_TIMEOUT):
                for rect in self.rects[: self.bar_loc]:
                    rect.setBrush(et.utils.pg_brush_cycler(0))

                for rect in self.rects[self.bar_loc :]:
                    rect.setBrush(et.utils.pg_brush_cycler(1))

                self.counter += 1
            else:
                for rect in self.rects:
                    rect.setBrush(et.utils.pg_brush_cycler(1))
                    self.bar_loc = 0

            level_html = self.level_html_format.format(level_text)
            self.level_text_item.setHtml(level_html)
            self.level_text_item.setPos(self.num_rects / 4.0, self.num_rects + 4.0)
            self.level_text_item.show()


class ViewPlugin(DetectorViewPluginBase):

    TEXT_MSG_MAP = {
        DetailedStatus.OK: "Ready to start.",
        DetailedStatus.CONTEXT_MISSING: "Run detector calibration.",
        DetailedStatus.CALIBRATION_MISSING: "Run detector calibration.",
        DetailedStatus.CONFIG_MISMATCH: (
            "Current configuration does not match the configuration "
            + "used during detector calibration. Run detector calibration."
        ),
    }

    def __init__(self, app_model: AppModel, view_widget: QWidget) -> None:
        super().__init__(app_model=app_model, view_widget=view_widget)
        self.app_model = app_model
        self._log = logging.getLogger(__name__)

        sticky_layout = QVBoxLayout()
        sticky_layout.setContentsMargins(0, 0, 0, 0)
        scrolly_layout = QVBoxLayout()
        scrolly_layout.setContentsMargins(0, 0, 0, 0)

        self.start_button = QPushButton(
            qta.icon("fa5s.play-circle", color=BUTTON_ICON_COLOR),
            "Start measurement",
            self.sticky_widget,
        )
        self.start_button.setShortcut("space")
        self.start_button.setToolTip("Starts the session.\n\nShortcut: Space")
        self.start_button.clicked.connect(self._send_start_request)

        self.stop_button = QPushButton(
            qta.icon("fa5s.stop-circle", color=BUTTON_ICON_COLOR),
            "Stop",
            self.sticky_widget,
        )
        self.stop_button.setShortcut("space")
        self.stop_button.setToolTip("Stops the session.\n\nShortcut: Space")
        self.stop_button.clicked.connect(self._send_stop_request)

        self.calibrate_detector_button = QPushButton(
            qta.icon("fa.circle", color=BUTTON_ICON_COLOR),
            "Calibrate detector",
            self.sticky_widget,
        )
        self.calibrate_detector_button.clicked.connect(self._on_calibrate_detector)

        self.defaults_button = QPushButton(
            qta.icon("mdi6.restore", color=BUTTON_ICON_COLOR),
            "Reset settings and calibrations",
            self.sticky_widget,
        )
        self.defaults_button.clicked.connect(self._send_defaults_request)

        self.message_box = QLabel(self.sticky_widget)
        self.message_box.setWordWrap(True)

        button_group = GridGroupBox("Controls", parent=self.sticky_widget)
        button_group.layout().addWidget(self.start_button, 0, 0)
        button_group.layout().addWidget(self.stop_button, 0, 1)
        button_group.layout().addWidget(self.calibrate_detector_button, 1, 0, 1, -1)
        button_group.layout().addWidget(self.defaults_button, 3, 0, 1, -1)
        button_group.layout().addWidget(self.message_box, 4, 0, 1, -1)

        sticky_layout.addWidget(button_group)

        sensor_selection_group = VerticalGroupBox("Sensor selection", parent=self.scrolly_widget)
        self.sensor_id_pidget = pidgets.SensorIdPidgetFactory(items=[]).create(
            parent=sensor_selection_group
        )
        self.sensor_id_pidget.sig_parameter_changed.connect(self._on_sensor_id_update)
        sensor_selection_group.layout().addWidget(self.sensor_id_pidget)
        scrolly_layout.addWidget(sensor_selection_group)

        self.tank_level_config_editor = AttrsConfigEditor[RefAppConfig](
            title="Tank level indicator parameters",
            factory_mapping=self._get_processor_pidget_mapping(),
            parent=self.scrolly_widget,
        )
        self.tank_level_config_editor.sig_update.connect(self._on_config_update)
        scrolly_layout.addWidget(self.tank_level_config_editor)

        self.config_editor = AttrsConfigEditor[RefAppConfig](
            title="Detector parameters",
            factory_mapping=self._get_detector_pidget_mapping(),
            parent=self.scrolly_widget,
        )
        self.config_editor.sig_update.connect(self._on_config_update)
        scrolly_layout.addWidget(self.config_editor)

        self.sticky_widget.setLayout(sticky_layout)
        self.scrolly_widget.setLayout(scrolly_layout)

    @classmethod
    def _get_processor_pidget_mapping(cls) -> PidgetFactoryMapping:
        return {
            "median_filter_length": pidgets.IntPidgetFactory(
                name_label_text="Median filter length",
                limits=(1, 10),
            ),
            "num_medians_to_average": pidgets.IntPidgetFactory(
                name_label_text="Num measurements averaged",
                limits=(1, 10),
            ),
            "start_m": pidgets.FloatPidgetFactory(
                name_label_text="Tank start",
                suffix=" m",
                decimals=3,
                limits=(0.03, 20),
            ),
            "end_m": pidgets.FloatPidgetFactory(
                name_label_text="Tank end",
                suffix=" m",
                decimals=3,
                limits=(0.05, 20),
            ),
        }

    @classmethod
    def _get_detector_pidget_mapping(cls) -> PidgetFactoryMapping:
        COMMON_PIDGETS = {
            "max_profile",
            "reflector_shape",
            "peaksorting_method",
            "threshold_method",
            "fixed_threshold_value",
            "num_frames_in_recorded_threshold",
            "threshold_sensitivity",
            "signal_quality",
        }

        return {
            "max_step_length": pidgets.OptionalIntPidgetFactory(
                name_label_text="Max step length",
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

    def on_backend_state_update(self, backend_plugin_state: Optional[SharedState]) -> None:
        if backend_plugin_state is not None and backend_plugin_state.config is not None:
            self.config_editor.set_data(backend_plugin_state.config)
            self.tank_level_config_editor.set_data(backend_plugin_state.config)

            results = backend_plugin_state.config._collect_validation_results()

            not_handled = self.tank_level_config_editor.handle_validation_results(results)
            not_handled = self.config_editor.handle_validation_results(not_handled)

            assert not_handled == []
        else:
            self.config_editor.set_data(None)
            self.tank_level_config_editor.set_data(None)

    def on_app_model_update(self, app_model: AppModel) -> None:
        state = app_model.backend_plugin_state

        if state is None:
            self.start_button.setEnabled(False)
            self.calibrate_detector_button.setEnabled(False)
            self.stop_button.setEnabled(False)
            self.defaults_button.setEnabled(False)

            self.config_editor.setEnabled(False)
            self.tank_level_config_editor.setEnabled(False)
            self.sensor_id_pidget.set_selected_sensor(None, [])
            self.message_box.setText("")

            return

        assert isinstance(state, SharedState)

        self.defaults_button.setEnabled(app_model.plugin_state == PluginState.LOADED_IDLE)

        self.tank_level_config_editor.setEnabled(app_model.plugin_state == PluginState.LOADED_IDLE)
        self.config_editor.setEnabled(app_model.plugin_state == PluginState.LOADED_IDLE)

        self.sensor_id_pidget.set_selected_sensor(state.sensor_id, app_model.connected_sensors)
        self.sensor_id_pidget.setEnabled(app_model.plugin_state.is_steady)

        detector_status = Detector.get_detector_status(
            state.config.to_detector_config(), state.context, [state.sensor_id]
        )

        self.message_box.setText(self.TEXT_MSG_MAP[detector_status.detector_state])

        app_model_ready = app_model.is_ready_for_session()
        try:
            state.config.validate()
        except a121.ValidationError:
            config_valid = False
        else:
            config_valid = True

        self.calibrate_detector_button.setEnabled(
            app_model_ready
            and config_valid
            and self.config_editor.is_ready
            and self.tank_level_config_editor.is_ready
        )
        self.start_button.setEnabled(
            detector_status.ready_to_start
            and app_model_ready
            and config_valid
            and self.config_editor.is_ready
            and self.tank_level_config_editor.is_ready
        )
        self.stop_button.setEnabled(app_model.plugin_state == PluginState.LOADED_BUSY)

    def _on_sensor_id_update(self, sensor_id: int) -> None:
        self.app_model.put_backend_plugin_task("update_sensor_id", {"sensor_id": sensor_id})

    def _on_config_update(self, config: RefAppConfig) -> None:
        self.app_model.put_backend_plugin_task("update_config", {"config": config})

    def handle_message(self, message: GeneralMessage) -> None:
        if message.name == "sync":
            self._log.debug(f"{type(self).__name__} syncing")

            self.config_editor.sync()
            self.tank_level_config_editor.sync()
        else:
            raise RuntimeError("Unknown message")

    # TODO: move to detector base (?)
    def _send_start_request(self) -> None:
        self.app_model.put_backend_plugin_task(
            "start_session",
            {"with_recorder": self.app_model.recording_enabled},
            on_error=self.app_model.emit_error,
        )

    # TODO: move to detector base (?)
    def _send_stop_request(self) -> None:
        self.app_model.put_backend_plugin_task("stop_session", on_error=self.app_model.emit_error)

    def _on_calibrate_detector(self) -> None:
        self.app_model.put_backend_plugin_task("calibrate_detector")

    def _send_defaults_request(self) -> None:
        self.app_model.put_backend_plugin_task("restore_defaults")


class PluginSpec(PluginSpecBase):
    def create_backend_plugin(
        self, callback: Callable[[Message], None], key: str
    ) -> BackendPlugin:
        return BackendPlugin(callback, generation=self.generation, key=key)

    def create_view_plugin(self, app_model: AppModel, view_widget: QWidget) -> ViewPlugin:
        return ViewPlugin(app_model=app_model, view_widget=view_widget)

    def create_plot_plugin(
        self, app_model: AppModel, plot_layout: pg.GraphicsLayout
    ) -> PlotPlugin:
        return PlotPlugin(app_model=app_model, plot_layout=plot_layout)


TANK_LEVEL_PLUGIN = PluginSpec(
    generation=PluginGeneration.A121,
    key="tank_level",
    title="Tank level",
    description="Measure liquid levels in tanks",
    family=PluginFamily.REF_APP,
    presets=[
        PluginPresetBase(name="Small", preset_id=PluginPresetId.SMALL),
        PluginPresetBase(name="Medium", preset_id=PluginPresetId.MEDIUM),
        PluginPresetBase(name="Large", preset_id=PluginPresetId.LARGE),
    ],
    default_preset_id=PluginPresetId.SMALL,
)
