# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import logging
from enum import Enum, auto
from typing import Any, Callable, Dict, Mapping, Optional

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
from acconeer.exptool.a121.algo.distance import (
    DetailedStatus,
    Detector,
    DetectorConfig,
    DetectorContext,
    DetectorResult,
)
from acconeer.exptool.a121.algo.distance._detector import _load_algo_data
from acconeer.exptool.a121.algo.distance._detector_plugin import ViewPlugin as DistanceViewPlugin
from acconeer.exptool.app.new import (
    BUTTON_ICON_COLOR,
    AppModel,
    AttrsConfigEditor,
    ConnectionState,
    GeneralMessage,
    GridGroupBox,
    HandledException,
    Message,
    PidgetFactoryMapping,
    PluginFamily,
    PluginGeneration,
    PluginPresetBase,
    PluginSpecBase,
    PluginState,
    PluginStateMessage,
    TwoSensorIdsEditor,
    is_task,
    pidgets,
)

from ._configs import get_default_detector_config
from ._processor import Processor, ProcessorConfig, ProcessorResult


log = logging.getLogger(__name__)


@attrs.mutable(kw_only=True)
class SharedState:
    sensor_ids: list[int] = attrs.field(factory=lambda: [1, 1])
    config: DetectorConfig = attrs.field(factory=DetectorConfig)
    bilateration_config: ProcessorConfig = attrs.field(factory=ProcessorConfig)
    context: DetectorContext = attrs.field(factory=DetectorContext)
    replaying: bool = attrs.field(default=False)


def serialized_attrs_instance_has_diverged(attrs_instance: Any) -> bool:
    """Checks (recursively) if a de-serialized attrs-instances contains
    all attributes defined its respective class definition.

    :param attrs_config:
        An instance of an attrs-class, that possibly contains other attrs-instances.
    :returns: True if any attrs-instance have diverged from its class, False otherwise
    """
    # TODO: Should end up in the `Config` ABC
    attrs_class = type(attrs_instance)
    if not attrs.has(attrs_class):
        raise TypeError(f"Cannot check object of type {attrs_class!r}. It's not an attrs-class.")

    for attribute in attrs_instance.__attrs_attrs__:
        try:
            value = getattr(attrs_instance, attribute.name)

            if attrs.has(type(value)) and serialized_attrs_instance_has_diverged(value):
                return True
        except AttributeError:
            log.info(
                f"Serialized object of type {attrs_class.__name__!r} "
                + "seems to have converged from its definition."
            )
            log.info(f"Should contain the attribute {attribute.name!r} but did not.")
            return True

    return False


class PluginPresetId(Enum):
    DEFAULT = auto()


@attrs.mutable(kw_only=True)
class BilaterationPreset:
    detector_config: DetectorConfig = attrs.field()
    bilateration_config: ProcessorConfig = attrs.field()


class BackendPlugin(DetectorBackendPluginBase[SharedState]):

    PLUGIN_PRESETS: Mapping[int, BilaterationPreset] = {
        PluginPresetId.DEFAULT.value: BilaterationPreset(
            detector_config=get_default_detector_config(),
            bilateration_config=ProcessorConfig(),
        )
    }

    def __init__(
        self, callback: Callable[[Message], None], generation: PluginGeneration, key: str
    ) -> None:
        super().__init__(callback=callback, generation=generation, key=key)

        self._detector_instance: Optional[Detector] = None

        self.restore_defaults()

    def _load_from_cache(self, file: h5py.File) -> None:
        self.shared_state.config = DetectorConfig.from_json(file["config"][()])
        self.shared_state.bilateration_config = ProcessorConfig.from_json(
            file["bilateration_config"][()]
        )
        self.shared_state.context = DetectorContext.from_h5(file["context"])

    @is_task
    def restore_defaults(self) -> None:
        self.shared_state = SharedState(config=get_default_detector_config())
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
    def update_processor_config(self, *, config: ProcessorConfig) -> None:
        self.shared_state.bilateration_config = config
        self.broadcast()

    @is_task
    def update_sensor_ids(self, *, sensor_ids: list[int]) -> None:
        self.shared_state.sensor_ids = sensor_ids
        self.broadcast()

    @is_task
    def set_preset(self, preset_id: int) -> None:
        preset_config = self.PLUGIN_PRESETS[preset_id]
        self.shared_state.config = preset_config.detector_config
        self.shared_state.bilateration_config = preset_config.bilateration_config
        self.broadcast(sync=True)

    def save_to_cache(self, file: h5py.File) -> None:
        _create_h5_string_dataset(file, "config", self.shared_state.config.to_json())
        _create_h5_string_dataset(
            file, "bilateration_config", self.shared_state.bilateration_config.to_json()
        )
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

        if recorder:
            algo_group = recorder.require_algo_group("bilateration")
        else:
            algo_group = None

        self._processor_instance = Processor(
            session_config=self._detector_instance.session_config,
            processor_config=self.shared_state.bilateration_config,
            sensor_ids=self.shared_state.sensor_ids,
        )

        self._detector_instance.start(
            recorder,
            _algo_group=algo_group,
        )

        self.callback(
            GeneralMessage(
                name="setup",
                kwargs={
                    "bilateration_config": self.shared_state.bilateration_config,
                    "num_curves": len(self._detector_instance.processor_specs),
                    "detector_config": self.shared_state.config,
                },
                recipient="plot_plugin",
            )
        )

    def end_session(self) -> None:
        if self._detector_instance is None:
            raise RuntimeError
        self._detector_instance.stop()

    def get_next(self) -> None:
        if self._detector_instance is None:
            raise RuntimeError
        detector_result = self._detector_instance.get_next()

        self._frame_count += 1

        processor_result = self._processor_instance.process(result=detector_result)

        assert self.client is not None
        self.callback(GeneralMessage(name="rate_stats", data=self.client._rate_stats))
        self.callback(GeneralMessage(name="frame_count", data=self._frame_count))
        self.callback(
            GeneralMessage(
                name="plot",
                kwargs={"detector_result": detector_result, "processor_result": processor_result},
                recipient="plot_plugin",
            ),
        )

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
    def __init__(self, *, plot_layout: pg.GraphicsLayout, app_model: AppModel) -> None:
        super().__init__(plot_layout=plot_layout, app_model=app_model)

    def setup_from_message(self, message: GeneralMessage) -> None:
        assert message.kwargs is not None
        self.setup(**message.kwargs)

    def update_from_message(self, message: GeneralMessage) -> None:
        self.update(**message.kwargs)  # type: ignore[arg-type]

    def setup(
        self,
        bilateration_config: ProcessorConfig,
        num_curves: int,
        detector_config: DetectorConfig,
    ) -> None:

        self.num_curves = num_curves
        self.detector_config = detector_config
        self.sensor_half_spacing_m = bilateration_config.sensor_spacing_m / 2

        win = self.plot_layout

        # Define sweep plot.
        self.sweep_plot = win.addPlot(row=0, col=0)
        self.sweep_plot.setMenuEnabled(False)
        self.sweep_plot.showGrid(x=True, y=True)
        self.sweep_plot.addLegend()
        self.sweep_plot.setLabel("left", "Amplitude")
        self.sweep_plot.setLabel("bottom", "Distance (m)")
        self.sweep_plot.addItem(pg.PlotDataItem())

        pen_sweep_0 = et.utils.pg_pen_cycler(0)
        pen_sweep_1 = et.utils.pg_pen_cycler(1)

        # Add sweep curves for the two sensors.
        feat_kw_1 = dict(pen=pen_sweep_0)
        feat_kw_2 = dict(pen=pen_sweep_1)
        self.sweep_curves_1 = [self.sweep_plot.plot(**feat_kw_1) for _ in range(self.num_curves)]
        self.sweep_curves_2 = [self.sweep_plot.plot(**feat_kw_2) for _ in range(self.num_curves)]

        pen_sweep_0 = et.utils.pg_pen_cycler(0, "--")
        pen_sweep_1 = et.utils.pg_pen_cycler(1, "--")

        # Add threshold curves for the two sensors.
        feat_kw_1 = dict(pen=pen_sweep_0)
        feat_kw_2 = dict(pen=pen_sweep_1)
        self.threshold_curves_1 = [
            self.sweep_plot.plot(**feat_kw_1) for _ in range(self.num_curves)
        ]
        self.threshold_curves_2 = [
            self.sweep_plot.plot(**feat_kw_2) for _ in range(self.num_curves)
        ]

        # Add legends.
        sweep_plot_legend = pg.LegendItem(offset=(0.0, 0.5))
        sweep_plot_legend.setParentItem(self.sweep_plot)
        sweep_plot_legend.addItem(self.sweep_curves_1[0], "Sweep - Left sensor")
        sweep_plot_legend.addItem(self.threshold_curves_1[0], "Threshold - Left sensor")
        sweep_plot_legend.addItem(self.sweep_curves_2[0], "Sweep - Right sensor")
        sweep_plot_legend.addItem(self.threshold_curves_2[0], "Threshold - Right sensor")

        self.sweep_smooth_max = et.utils.SmoothMax()

        # Define obstacle plot.
        self.obstacle_location_plot = win.addPlot(row=1, col=0)
        self.obstacle_location_plot.setMenuEnabled(False)
        self.obstacle_location_plot.setAspectLocked()
        self.obstacle_location_plot.showGrid(x=True, y=True)
        self.obstacle_location_plot.addLegend()
        self.obstacle_location_plot.setLabel("left", "Y (m)")
        self.obstacle_location_plot.setLabel("bottom", "X (m)")
        self.obstacle_location_plot.addItem(pg.PlotDataItem())
        self.obstacle_location_plot.setXRange(
            -self.detector_config.end_m, self.detector_config.end_m
        )
        self.obstacle_location_plot.setYRange(0.0, self.detector_config.end_m)

        pen_sweep_0 = et.utils.pg_pen_cycler(0)
        brush_sweep_0 = et.utils.pg_brush_cycler(0)
        symbol_kw = dict(symbol="o", symbolSize=10, symbolBrush=brush_sweep_0, symbolPen=None)
        feat_kw = dict(pen=None, **symbol_kw)
        self.obstacle_location_curve = self.obstacle_location_plot.plot(**feat_kw)
        feat_kw = dict(pen=pen_sweep_0)
        self.obstacle_location_half_curve = [
            self.obstacle_location_plot.plot(**feat_kw) for _ in range(Processor._MAX_NUM_OBJECTS)
        ]

    def update(
        self, *, detector_result: Dict[int, DetectorResult], processor_result: ProcessorResult
    ) -> None:
        # Plot sweep data from both distance detectors.
        max_val = 0.0
        for distance_detector_result, sweep_curves, threshold_curves in zip(
            detector_result.values(),
            [self.sweep_curves_1, self.sweep_curves_2],
            [self.threshold_curves_1, self.threshold_curves_2],
        ):
            for idx, distance_processor_result in enumerate(
                distance_detector_result.processor_results
            ):

                abs_sweep = distance_processor_result.extra_result.abs_sweep
                threshold = distance_processor_result.extra_result.used_threshold
                distances_m = distance_processor_result.extra_result.distances_m

                assert abs_sweep is not None
                assert threshold is not None
                assert distances_m is not None

                sweep_curves[idx].setData(distances_m, abs_sweep)
                threshold_curves[idx].setData(distances_m, threshold)

                if max_val < np.max(abs_sweep):
                    max_val = float(np.max(abs_sweep))

                if max_val < np.max(threshold):
                    max_val = float(np.max(threshold))

        if max_val != 0.0:
            self.sweep_plot.setYRange(0.0, self.sweep_smooth_max.update(max_val))

        # Plot result from bilateration processor.
        # Start with the points.
        points = processor_result.points
        xs = [point.x_coord for point in points]
        ys = [point.y_coord for point in points]
        self.obstacle_location_curve.setData(xs, ys)

        # Plot objects without counter part.
        objects_without_counterpart = processor_result.objects_without_counterpart
        num_points_on_circle = 100
        for i, o in enumerate(objects_without_counterpart):
            x = np.cos(np.linspace(0, np.pi, num_points_on_circle)) * o.distance
            y = np.sin(np.linspace(0, np.pi, num_points_on_circle)) * o.distance

            # Offset circle to center around the sensor that detected the object.
            if o.sensor_position == Processor._SENSOR_POSITION_LEFT:
                x -= self.sensor_half_spacing_m
            elif o.sensor_position == Processor._SENSOR_POSITION_RIGHT:
                x += self.sensor_half_spacing_m
            else:
                raise ValueError("Invalid sensor position.")

            self.obstacle_location_half_curve[i].setData(x, y)

        # Remove curves that does not have an object to visualize.
        for i in range(len(objects_without_counterpart), Processor._MAX_NUM_OBJECTS):
            self.obstacle_location_half_curve[i].setData([], [])


class ViewPlugin(DetectorViewPluginBase):

    TEXT_MSG_MAP = {
        DetailedStatus.OK: "Ready to start.",
        DetailedStatus.SENSOR_IDS_NOT_UNIQUE: "Select two different sensor IDs.",
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

        sensor_selection_group = GridGroupBox("Sensor selection", parent=self.scrolly_widget)
        self.two_sensor_id_editor = TwoSensorIdsEditor(name_label_texts=["Left", "Right"])
        sensor_selection_group.layout().addWidget(self.two_sensor_id_editor, 0, 0)
        scrolly_layout.addWidget(sensor_selection_group)

        self.bilateration_config_editor = AttrsConfigEditor[ProcessorConfig](
            title="Bilateration parameters",
            factory_mapping=self._get_processor_pidget_mapping(),
            parent=self.scrolly_widget,
        )
        self.bilateration_config_editor.sig_update.connect(self._on_processor_config_update)
        scrolly_layout.addWidget(self.bilateration_config_editor)

        self.config_editor = AttrsConfigEditor[DetectorConfig](
            title="Distance detector parameters",
            factory_mapping=self._get_pidget_mapping(),
            parent=self.scrolly_widget,
        )
        self.config_editor.sig_update.connect(self._on_config_update)
        scrolly_layout.addWidget(self.config_editor)

        self.two_sensor_id_editor.sig_update.connect(self._on_sensor_ids_update)
        self.sticky_widget.setLayout(sticky_layout)
        self.scrolly_widget.setLayout(scrolly_layout)

    @classmethod
    def _get_processor_pidget_mapping(cls) -> PidgetFactoryMapping:
        return {
            "sensor_spacing_m": pidgets.FloatParameterWidgetFactory(
                name_label_text="Sensor spacing",
                suffix=" m",
                decimals=3,
            ),
            "max_anticipated_velocity_mps": pidgets.FloatParameterWidgetFactory(
                name_label_text="Max anticipated velocity",
                suffix=" m/s",
                decimals=1,
            ),
            "dead_reckoning_duration_s": pidgets.FloatParameterWidgetFactory(
                name_label_text="Dead reckoning duration",
                suffix=" s",
                decimals=1,
            ),
            "sensitivity": pidgets.FloatSliderParameterWidgetFactory(
                name_label_text="Sensitivity",
                decimals=2,
                limits=(0.001, 1),
                show_limit_values=False,
                limit_texts=("Higher robustness", "More Responsive"),
            ),
        }

    @classmethod
    def _get_pidget_mapping(cls) -> PidgetFactoryMapping:
        distance_pidget_mapping = dict(DistanceViewPlugin.get_pidget_mapping())

        # Bilateration requires an update rate, so replace the optional float with a mandatory
        distance_pidget_mapping["update_rate"] = pidgets.FloatParameterWidgetFactory(
            name_label_text="Update rate",
            decimals=1,
            limits=(1, None),
        )
        return distance_pidget_mapping

    def on_app_model_update(self, app_model: AppModel) -> None:
        state = app_model.backend_plugin_state

        if state is None:
            self.start_button.setEnabled(False)
            self.calibrate_detector_button.setEnabled(False)
            self.stop_button.setEnabled(False)
            self.defaults_button.setEnabled(False)

            self.config_editor.set_data(None)
            self.config_editor.setEnabled(False)
            self.bilateration_config_editor.set_data(None)
            self.bilateration_config_editor.setEnabled(False)
            self.two_sensor_id_editor.set_selected_sensors(None, [])
            self.message_box.setText("")

            return

        assert isinstance(state, SharedState)

        self.defaults_button.setEnabled(app_model.plugin_state == PluginState.LOADED_IDLE)

        self.config_editor.setEnabled(app_model.plugin_state == PluginState.LOADED_IDLE)
        self.config_editor.set_data(state.config)
        self.bilateration_config_editor.setEnabled(
            app_model.plugin_state == PluginState.LOADED_IDLE
        )
        self.bilateration_config_editor.set_data(state.bilateration_config)
        self.two_sensor_id_editor.set_selected_sensors(
            state.sensor_ids, app_model.connected_sensors
        )
        self.two_sensor_id_editor.setEnabled(app_model.plugin_state.is_steady)

        detector_status = Detector.get_detector_status(
            state.config, state.context, state.sensor_ids
        )

        self.message_box.setText(self.TEXT_MSG_MAP[detector_status.detector_state])

        ready_for_session = (
            app_model.plugin_state == PluginState.LOADED_IDLE
            and app_model.connection_state == ConnectionState.CONNECTED
        )
        self.calibrate_detector_button.setEnabled(
            ready_for_session
            and not detector_status.detector_state == DetailedStatus.SENSOR_IDS_NOT_UNIQUE
        )
        self.start_button.setEnabled(ready_for_session and detector_status.ready_to_start)
        self.stop_button.setEnabled(app_model.plugin_state == PluginState.LOADED_BUSY)

    def _on_config_update(self, config: DetectorConfig) -> None:
        self.app_model.put_backend_plugin_task("update_config", {"config": config})

    def _on_processor_config_update(self, config: ProcessorConfig) -> None:
        self.app_model.put_backend_plugin_task("update_processor_config", {"config": config})

    def _on_sensor_ids_update(self, sensor_ids: list[int]) -> None:
        self.app_model.put_backend_plugin_task("update_sensor_ids", {"sensor_ids": sensor_ids})

    def handle_message(self, message: GeneralMessage) -> None:
        if message.name == "sync":
            log.debug(f"{type(self).__name__} syncing")

            self.config_editor.sync()
            self.bilateration_config_editor.sync()
        else:
            raise RuntimeError("Unknown message")

    def _on_calibrate_detector(self) -> None:
        self.app_model.put_backend_plugin_task("calibrate_detector")
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


BILATERATION_PLUGIN = PluginSpec(
    generation=PluginGeneration.A121,
    key="bilateration",
    title="Bilateration",
    description="Use two sensors to estimate distance and angle.",
    family=PluginFamily.EXAMPLE_APP,
    presets=[
        PluginPresetBase(name="Default", preset_id=PluginPresetId.DEFAULT),
    ],
    default_preset_id=PluginPresetId.DEFAULT,
)
