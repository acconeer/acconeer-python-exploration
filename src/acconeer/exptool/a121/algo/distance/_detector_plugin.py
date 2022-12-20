# Copyright (c) Acconeer AB, 2022
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
from acconeer.exptool.app.new import (
    BUTTON_ICON_COLOR,
    AppModel,
    AttrsConfigEditor,
    BackendLogger,
    GeneralMessage,
    GridGroupBox,
    HandledException,
    Message,
    MiscErrorView,
    PidgetFactoryMapping,
    PluginFamily,
    PluginGeneration,
    PluginPresetBase,
    PluginSpecBase,
    PluginState,
    PluginStateMessage,
    VerticalGroupBox,
    is_task,
    pidgets,
)

from ._detector import (
    DetailedStatus,
    Detector,
    DetectorConfig,
    DetectorContext,
    DetectorResult,
    PeakSortingMethod,
    ThresholdMethod,
    _load_algo_data,
)


@attrs.mutable(kw_only=True)
class SharedState:
    sensor_ids: list[int] = attrs.field(factory=lambda: [1])
    config: DetectorConfig = attrs.field(factory=DetectorConfig)
    context: DetectorContext = attrs.field(factory=DetectorContext)


class PluginPresetId(Enum):
    DEFAULT = auto()


class BackendPlugin(DetectorBackendPluginBase[SharedState]):

    PLUGIN_PRESETS: Mapping[int, Callable[[], DetectorConfig]] = {
        PluginPresetId.DEFAULT.value: lambda: DetectorConfig()
    }

    def __init__(
        self, callback: Callable[[Message], None], generation: PluginGeneration, key: str
    ) -> None:
        super().__init__(callback=callback, generation=generation, key=key)
        self._detector_instance: Optional[Detector] = None
        self._log = BackendLogger.getLogger(__name__)

        self.restore_defaults()

    def _load_from_cache(self, file: h5py.File) -> None:
        self.shared_state.config = DetectorConfig.from_json(file["config"][()])
        self.shared_state.context = DetectorContext.from_h5(file["context"])

    @is_task
    def restore_defaults(self) -> None:
        self.shared_state = SharedState()
        self.broadcast(sync=True)

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
        self.broadcast(sync=True)

    def save_to_cache(self, file: h5py.File) -> None:
        _create_h5_string_dataset(file, "config", self.shared_state.config.to_json())
        context_group = file.create_group("context")
        self.shared_state.context.to_h5(context_group)

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
            GeneralMessage(
                name="setup",
                kwargs=dict(num_curves=len(self._detector_instance.processor_specs)),
                recipient="plot_plugin",
            )
        )

    def end_session(self) -> None:
        assert self._detector_instance
        self._detector_instance.stop()

    def get_next(self) -> None:
        if self._detector_instance is None:
            raise RuntimeError

        assert self.client
        result = self._detector_instance.get_next()

        self._frame_count += 1

        self.callback(GeneralMessage(name="rate_stats", data=self.client._rate_stats))
        self.callback(GeneralMessage(name="frame_count", data=self._frame_count))
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
            self._detector_instance = Detector(
                client=self.client,
                sensor_ids=self.shared_state.sensor_ids,
                detector_config=self.shared_state.config,
                context=None,
            )
            self._detector_instance.calibrate_detector()
        except Exception as exc:
            raise HandledException("Failed to calibrate detector") from exc
        finally:
            self.callback(PluginStateMessage(state=PluginState.LOADED_IDLE))

        self.shared_state.context = self._detector_instance.context
        self.broadcast()


class PlotPlugin(DetectorPlotPluginBase):

    _DISTANCE_HISTORY_PLOT_HALF_SPAN = 0.2

    def __init__(self, *, plot_layout: pg.GraphicsLayout, app_model: AppModel) -> None:
        super().__init__(plot_layout=plot_layout, app_model=app_model)

    def setup_from_message(self, message: GeneralMessage) -> None:
        assert message.kwargs is not None
        self.setup(**message.kwargs)

    def update_from_message(self, message: GeneralMessage) -> None:
        self.update(message.data)  # type: ignore[arg-type]

    def setup(self, num_curves: int) -> None:
        self.num_curves = num_curves
        self.distance_history = [np.NaN] * 100

        win = self.plot_layout

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

        self.dist_history_plot = win.addPlot(row=1, col=0)
        self.dist_history_plot.setMenuEnabled(False)
        self.dist_history_plot.showGrid(x=True, y=True)
        self.dist_history_plot.addLegend()
        self.dist_history_plot.setLabel("left", "Estimated distance (m)")
        self.dist_history_plot.addItem(pg.PlotDataItem())
        self.dist_history_plot.setXRange(0, len(self.distance_history))

        pen = et.utils.pg_pen_cycler(0)
        brush = et.utils.pg_brush_cycler(0)
        symbol_kw = dict(symbol="o", symbolSize=5, symbolBrush=brush, symbolPen="k")
        feat_kw = dict(pen=pen, **symbol_kw)
        self.dist_history_curve = self.dist_history_plot.plot(**feat_kw)

        self.sweep_smooth_max = et.utils.SmoothMax()
        self.distance_hist_smooth_lim = et.utils.SmoothLimits()

    def update(self, multi_sensor_result: dict[int, DetectorResult]) -> None:
        # Get the first element as the plugin only supports single sensor operation.
        (result,) = list(multi_sensor_result.values())

        assert result.distances is not None

        self.distance_history.pop(0)
        if len(result.distances) != 0:
            self.distance_history.append(result.distances[0])
        else:
            self.distance_history.append(np.nan)

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

        if np.any(~np.isnan(self.distance_history)):
            self.dist_history_curve.setData(self.distance_history)
            distance_span = distances_m[-1] - distances_m[0]
            lims = self.distance_hist_smooth_lim.update(self.distance_history)
            lower_lim = max(0.0, lims[0] - distance_span * self._DISTANCE_HISTORY_PLOT_HALF_SPAN)
            upper_lim = lims[1] + distance_span * self._DISTANCE_HISTORY_PLOT_HALF_SPAN
            self.dist_history_plot.setYRange(lower_lim, upper_lim)
        else:
            self.dist_history_curve.setData([])


class ViewPlugin(DetectorViewPluginBase):

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
        DetailedStatus.INVALID_DETECTOR_CONFIG_RANGE: (
            "Invalid detector config. Valid measurement"
            + " range is "
            + str(Detector.MIN_DIST_M)
            + "-"
            + str(Detector.MAX_DIST_M)
            + "m."
        ),
    }

    def __init__(self, app_model: AppModel, view_widget: QWidget) -> None:
        super().__init__(app_model=app_model, view_widget=view_widget)
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

        self.misc_error_view = MiscErrorView(self.scrolly_widget)
        scrolly_layout.addWidget(self.misc_error_view)

        sensor_selection_group = VerticalGroupBox("Sensor selection", parent=self.scrolly_widget)
        self.sensor_id_pidget = pidgets.SensorIdParameterWidgetFactory(items=[]).create(
            parent=sensor_selection_group
        )
        self.sensor_id_pidget.sig_parameter_changed.connect(self._on_sensor_id_update)
        sensor_selection_group.layout().addWidget(self.sensor_id_pidget)
        scrolly_layout.addWidget(sensor_selection_group)

        self.config_editor = AttrsConfigEditor[DetectorConfig](
            title="Detector parameters",
            factory_mapping=self.get_pidget_mapping(),
            parent=self.scrolly_widget,
        )
        self.config_editor.sig_update.connect(self._on_config_update)
        scrolly_layout.addWidget(self.config_editor)

        self.sticky_widget.setLayout(sticky_layout)
        self.scrolly_widget.setLayout(scrolly_layout)

    @classmethod
    def get_pidget_mapping(cls) -> PidgetFactoryMapping:
        return {
            "start_m": pidgets.FloatParameterWidgetFactory(
                name_label_text="Range start",
                suffix=" m",
                decimals=3,
            ),
            "end_m": pidgets.FloatParameterWidgetFactory(
                name_label_text="Range end",
                suffix=" m",
                decimals=3,
            ),
            "max_step_length": pidgets.OptionalIntParameterWidgetFactory(
                name_label_text="Max step length",
                checkbox_label_text="Set",
                limits=(1, None),
                init_set_value=12,
            ),
            "max_profile": pidgets.EnumParameterWidgetFactory(
                name_label_text="Max profile",
                enum_type=a121.Profile,
                label_mapping={
                    a121.Profile.PROFILE_1: "1 (shortest)",
                    a121.Profile.PROFILE_2: "2",
                    a121.Profile.PROFILE_3: "3",
                    a121.Profile.PROFILE_4: "4",
                    a121.Profile.PROFILE_5: "5 (longest)",
                },
            ),
            "num_frames_in_recorded_threshold": pidgets.IntParameterWidgetFactory(
                name_label_text="Num frames in rec. thr.",
                limits=(1, None),
            ),
            "threshold_method": pidgets.EnumParameterWidgetFactory(
                name_label_text="Threshold method",
                enum_type=ThresholdMethod,
                label_mapping={
                    ThresholdMethod.CFAR: "CFAR",
                    ThresholdMethod.FIXED: "Fixed",
                    ThresholdMethod.RECORDED: "Recorded",
                },
            ),
            "peaksorting_method": pidgets.EnumParameterWidgetFactory(
                name_label_text="Peak sorting method",
                enum_type=PeakSortingMethod,
                label_mapping={
                    PeakSortingMethod.CLOSEST: "Closest",
                    PeakSortingMethod.HIGHEST_RCS: "Highest RCS",
                },
            ),
            "fixed_threshold_value": pidgets.FloatParameterWidgetFactory(
                name_label_text="Fixed threshold value",
                decimals=1,
                limits=(0, None),
            ),
            "threshold_sensitivity": pidgets.FloatSliderParameterWidgetFactory(
                name_label_text="Threshold sensitivity",
                decimals=2,
                limits=(0, 1),
                show_limit_values=False,
            ),
            "signal_quality": pidgets.FloatSliderParameterWidgetFactory(
                name_label_text="Signal quality",
                decimals=1,
                limits=(-10, 35),
                show_limit_values=False,
                limit_texts=("Less power", "Higher quality"),
            ),
            "update_rate": pidgets.OptionalFloatParameterWidgetFactory(
                name_label_text="Update rate",
                checkbox_label_text="Set",
                limits=(1, None),
                init_set_value=20,
            ),
        }

    def on_backend_state_update(self, backend_plugin_state: Optional[SharedState]) -> None:
        if backend_plugin_state is not None and backend_plugin_state.config is not None:
            results = backend_plugin_state.config._collect_validation_results()

            not_handled = self.config_editor.handle_validation_results(results)

            not_handled = self.misc_error_view.handle_validation_results(not_handled)

            assert not_handled == []

    def on_app_model_update(self, app_model: AppModel) -> None:
        state = app_model.backend_plugin_state
        if state is None:
            self.start_button.setEnabled(False)
            self.calibrate_detector_button.setEnabled(False)
            self.stop_button.setEnabled(False)
            self.defaults_button.setEnabled(False)

            self.config_editor.set_data(None)
            self.config_editor.setEnabled(False)
            self.sensor_id_pidget.set_selected_sensor(None, [])
            self.message_box.setText("")

            return

        assert isinstance(state, SharedState)

        self.defaults_button.setEnabled(app_model.plugin_state == PluginState.LOADED_IDLE)

        self.config_editor.setEnabled(app_model.plugin_state == PluginState.LOADED_IDLE)
        self.config_editor.set_data(state.config)

        (sensor_id,) = state.sensor_ids
        self.sensor_id_pidget.set_selected_sensor(sensor_id, app_model.connected_sensors)
        self.sensor_id_pidget.setEnabled(app_model.plugin_state.is_steady)

        detector_status = Detector.get_detector_status(
            state.config, state.context, state.sensor_ids
        )

        self.message_box.setText(self.TEXT_MSG_MAP[detector_status.detector_state])

        ready_for_session = app_model.is_ready_for_session()

        self.calibrate_detector_button.setEnabled(ready_for_session)
        self.start_button.setEnabled(ready_for_session and detector_status.ready_to_start)
        self.stop_button.setEnabled(app_model.plugin_state == PluginState.LOADED_BUSY)

    def _on_sensor_id_update(self, sensor_id: int) -> None:
        self.app_model.put_backend_plugin_task("update_sensor_ids", {"sensor_ids": [sensor_id]})

    def _on_config_update(self, config: DetectorConfig) -> None:
        self.app_model.put_backend_plugin_task("update_config", {"config": config})

    def handle_message(self, message: GeneralMessage) -> None:
        if message.name == "sync":
            self._log.debug(f"{type(self).__name__} syncing")

            self.config_editor.sync()
        else:
            raise RuntimeError("Unknown message")

    def _on_calibrate_detector(self) -> None:
        self.app_model.put_backend_plugin_task(
            "calibrate_detector", on_error=self.app_model.emit_error
        )
        self.app_model.set_plugin_state(PluginState.LOADED_STARTING)

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


DISTANCE_DETECTOR_PLUGIN = PluginSpec(
    generation=PluginGeneration.A121,
    key="distance_detector",
    title="Distance detector",
    description="Easily measure distance to objects.",
    family=PluginFamily.DETECTOR,
    presets=[
        PluginPresetBase(name="Default", preset_id=PluginPresetId.DEFAULT),
    ],
    default_preset_id=PluginPresetId.DEFAULT,
)
