# Copyright (c) Acconeer AB, 2023-2025
# All rights reserved

from __future__ import annotations

import logging
from enum import Enum, auto
from typing import Callable, Mapping, Optional

import attrs
import h5py
import numpy as np

from PySide6 import QtCore
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
from acconeer.exptool.a121.algo._utils import get_distances_m
from acconeer.exptool.a121.algo.parking import (
    ObstructionProcessor,
    get_ground_config,
    get_pole_config,
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
    PidgetGroupFactoryMapping,
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

from ._processors import MAX_AMPLITUDE
from ._ref_app import (
    DetailedStatus,
    RefApp,
    RefAppConfig,
    RefAppContext,
    RefAppResult,
    _load_algo_data,
    get_sensor_configs,
)


log = logging.getLogger(__name__)


@attrs.mutable(kw_only=True)
class SharedState:
    sensor_id: int = attrs.field(default=1)
    config: RefAppConfig = attrs.field(factory=get_ground_config)
    context: RefAppContext = attrs.field(default=None)


class PluginPresetId(Enum):
    GROUND = auto()
    POLE = auto()


@attrs.frozen(kw_only=True)
class SetupMessage(GeneralMessage):
    ref_app_config: RefAppConfig
    session_config: a121.SessionConfig
    sensor_id: int
    metadata: a121.Metadata
    name: str = attrs.field(default="setup", init=False)
    recipient: backend.RecipientLiteral = attrs.field(default="plot_plugin", init=False)


class BackendPlugin(A121BackendPluginBase[SharedState]):
    PLUGIN_PRESETS: Mapping[int, Callable[[], RefAppConfig]] = {
        PluginPresetId.GROUND.value: lambda: get_ground_config(),
        PluginPresetId.POLE.value: lambda: get_pole_config(),
    }

    def __init__(
        self,
        callback: Callable[[Message], None],
        generation: PluginGeneration,
        key: str,
    ) -> None:
        super().__init__(callback=callback, generation=generation, key=key)

        self._recorder: Optional[a121.H5Recorder] = None
        self._ref_app_instance: Optional[RefApp] = None
        self._log = BackendLogger.getLogger(__name__)

        self.restore_defaults()

    def _load_from_cache(self, file: h5py.File) -> None:
        self.shared_state.config = RefAppConfig.from_json(file["config"][()])

        context = opser.try_deserialize(file["context"], RefAppContext)
        if context is None:
            self.send_status_message(
                "Could not load cached context. Falling back to empty context"
            )
            context = RefAppContext()

        self.shared_state.context = context

    @is_task
    def restore_defaults(self) -> None:
        self.shared_state = SharedState()
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
    def update_config(self, *, config: RefAppConfig) -> None:
        self.shared_state.config = config
        self.broadcast()

    def save_to_cache(self, file: h5py.File) -> None:
        _create_h5_string_dataset(file, "config", self.shared_state.config.to_json())
        opser.serialize(self.shared_state.context, file.create_group("context"))

    @is_task
    def set_preset(self, preset_id: int) -> None:
        preset_config = self.PLUGIN_PRESETS[preset_id]
        self.shared_state.config = preset_config()
        self.broadcast()

    def load_from_record_setup(self, *, record: a121.H5Record) -> None:
        algo_group = record.get_algo_group(self.key)
        sensor_id, config, context = _load_algo_data(algo_group)
        self.shared_state.config = config
        self.shared_state.sensor_id = sensor_id
        self.shared_state.context = context

    def _start_session(self, recorder: Optional[a121.H5Recorder]) -> None:
        assert self.client
        self._ref_app_instance = RefApp(
            client=self.client,
            sensor_id=self.shared_state.sensor_id,
            ref_app_config=self.shared_state.config,
            context=self.shared_state.context,
        )
        self._ref_app_instance.start(recorder)

        metadata = self.client.extended_metadata[0][self.shared_state.sensor_id]
        self.callback(
            SetupMessage(
                ref_app_config=self.shared_state.config,
                metadata=metadata,
                sensor_id=self.shared_state.sensor_id,
                session_config=self.client.session_config,
            )
        )

    def end_session(self) -> None:
        if self._ref_app_instance is None:
            raise RuntimeError
        self._ref_app_instance.stop()

    def get_next(self) -> None:
        assert self.client
        if self._ref_app_instance is None:
            raise RuntimeError
        result = self._ref_app_instance.get_next()

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
            self._ref_app_instance = RefApp(
                client=self.client,
                sensor_id=self.shared_state.sensor_id,
                ref_app_config=self.shared_state.config,
                context=RefAppContext(),
            )
            self._ref_app_instance.calibrate_ref_app()
        except Exception as exc:
            msg = "Failed to calibrate detector"
            raise HandledException(msg) from exc
        finally:
            self.callback(PluginStateMessage(state=PluginState.LOADED_IDLE))

        self.shared_state.context = self._ref_app_instance.context
        self.broadcast()


class PlotPlugin(PgPlotPlugin):
    def __init__(self, app_model: AppModel) -> None:
        super().__init__(app_model=app_model)
        self._plot_job: Optional[RefAppResult] = None
        self._is_setup = False
        self.obstruction_text_timeout = 0

    def handle_message(self, message: backend.GeneralMessage) -> None:
        if isinstance(message, backend.PlotMessage):
            self._plot_job = message.result
        elif isinstance(message, SetupMessage):
            self.setup(
                message.ref_app_config,
                message.metadata,
                message.sensor_id,
                message.session_config,
            )
            self._is_setup = True
        else:
            log.warn(f"{self.__class__.__name__} got an unsupported command: {message.name!r}.")

    def draw(self) -> None:
        if not self._is_setup or self._plot_job is None:
            return
        try:
            self.draw_plot_job(ref_app_result=self._plot_job)
        finally:
            self._plot_job = None

    def setup(
        self,
        ref_app_config: RefAppConfig,
        metadata: a121.Metadata,
        sensor_id: int,
        session_config: a121.SessionConfig,
    ) -> None:
        self.plot_layout.clear()

        self.metadata = metadata
        self.ref_app_config = ref_app_config
        sensor_configs = get_sensor_configs(ref_app_config)
        display_config = sensor_configs["base_config"]
        self.sensor_id = sensor_id
        self.session_config = session_config
        self.sensor_config = display_config
        self.distances = get_distances_m(display_config, metadata)

        if self.ref_app_config.obstruction_detection:
            obstruction_config = sensor_configs["obstruction_config"]
            self.obs_distances = get_distances_m(obstruction_config, metadata)
            self.obs_x_thres, self.obs_y_thres = ObstructionProcessor.get_thresholds(
                ref_app_config.obstruction_distance_threshold, self.obs_distances
            )

        win = self.plot_layout
        # Define pens and font.
        blue_color = et.utils.color_cycler(0)
        orange_color = et.utils.color_cycler(1)
        brush = et.utils.pg_brush_cycler(0)

        self.blue = dict(
            pen=pg.mkPen(blue_color, width=2),
            symbol="o",
            symbolSize=1,
            symbolBrush=brush,
            symbolPen="k",
        )
        self.orange = dict(
            pen=pg.mkPen(orange_color, width=2),
            symbol="o",
            symbolSize=1,
            symbolBrush=brush,
            symbolPen="k",
        )
        self.blue_transparent_pen = pg.mkPen(f"{blue_color}50", width=2)
        self.orange_transparent_pen = pg.mkPen(f"{orange_color}50", width=2)

        brush_dot = et.utils.pg_brush_cycler(1)

        # Signature plot.
        self.sig_plot = win.addPlot(row=0, col=0, colspan=2)
        self.sig_plot.setTitle("Sampled Signatures")
        self.sig_plot.setMenuEnabled(False)
        self.sig_plot.showGrid(x=True, y=True)
        self.sig_plot.addLegend()
        self.sig_plot.setLabel("left", "Normalized energy")
        self.sig_plot.setLabel("bottom", "Distance (m)")
        self.sig_plot.addItem(pg.PlotDataItem())
        self.sig_plot_x_range = (
            min(self.distances),
            max(self.distances) + ref_app_config.weighted_distance_threshold_m,
        )
        self.sig_plot.setXRange(self.sig_plot_x_range[0], self.sig_plot_x_range[1])
        self.sig_plot.setYRange(0, 100)
        symbol_kw_main = dict(
            symbol="o", symbolSize=7, symbolBrush=brush, symbolPen=None, pen=None
        )
        self.sig_plot_curve = self.sig_plot.plot(**symbol_kw_main)
        energy_threshold_line = pg.InfiniteLine(
            angle=0, pen=pg.mkPen("k", width=1.5, style=QtCore.Qt.PenStyle.DashLine)
        )
        energy_threshold_line.setVisible(True)
        energy_threshold_line.setPos(ref_app_config.amplitude_threshold)
        self.sig_plot.addItem(energy_threshold_line)

        self.sig_plot_cluster_start = pg.InfiniteLine(angle=90, pen=pg.mkPen("k", width=1.5))
        self.sig_plot_cluster_start.setVisible(True)
        self.sig_plot.addItem(self.sig_plot_cluster_start)

        self.sig_plot_cluster_end = pg.InfiniteLine(angle=90, pen=pg.mkPen("k", width=1.5))
        self.sig_plot_cluster_end.setVisible(True)
        self.sig_plot.addItem(self.sig_plot_cluster_end)

        self.sig_plot_smooth_max = et.utils.SmoothMax(self.session_config.update_rate)

        parking_car_html = (
            '<div style="text-align: center">'
            '<span style="color: #FFFFFF;font-size:15pt;">'
            "{}</span></div>".format("Parked car detected!")
        )
        self.parking_car_text_item = pg.TextItem(
            html=parking_car_html,
            fill=orange_color,
            anchor=(0.5, 0),
        )
        parking_no_car_html = (
            '<div style="text-align: center">'
            '<span style="color: #FFFFFF;font-size:15pt;">'
            "{}</span></div>".format("No car detected.")
        )
        self.parking_no_car_text_item = pg.TextItem(
            html=parking_no_car_html,
            fill=blue_color,
            anchor=(0.5, 0),
        )

        self.sig_plot.addItem(self.parking_car_text_item)
        self.sig_plot.addItem(self.parking_no_car_text_item)
        self.parking_car_text_item.hide()
        self.parking_no_car_text_item.hide()

        self.cluster_width = ref_app_config.weighted_distance_threshold_m

        # Obstruction plot.
        if self.ref_app_config.obstruction_detection:
            self.obstruction_plot = win.addPlot(row=1, col=1)
            self.obstruction_plot.setTitle("Obstruction Detection Signatures")
            self.obstruction_plot.setMenuEnabled(False)
            self.obstruction_plot.showGrid(x=True, y=True)
            self.obstruction_plot.addLegend()
            self.obstruction_plot.setLabel("left", "Average energy")
            self.obstruction_plot.setLabel("bottom", "Distance (m)")
            self.obstruction_plot.addItem(pg.PlotDataItem())
            self.obstruction_plot.setXRange(min(self.obs_distances), max(self.obs_distances))
            self.obstruction_plot.setYRange(0, MAX_AMPLITUDE)  # Set to standard
            self.obstruction_plot_curve = self.obstruction_plot.plot(**self.orange)

            symbol_obstruction_dot = dict(
                symbol="o",
                symbolSize=7,
                symbolBrush=brush_dot,
                symbolPen=None,
                pen=None,
            )
            self.obstruction_plot_point = self.obstruction_plot.plot(**symbol_obstruction_dot)

            symbol_kw_main = dict(
                symbol="o", symbolSize=7, symbolBrush=brush, symbolPen=None, pen=None
            )
            self.obstruction_plot_center = self.obstruction_plot.plot(**symbol_kw_main)

            self.obstruction_center_rect = pg.QtWidgets.QGraphicsRectItem(0, 0, 0.01, 0.01)
            self.obstruction_center_rect.setPen(self.orange_transparent_pen)
            self.obstruction_plot.addItem(self.obstruction_center_rect)

            obstruction_html = (
                '<div style="text-align: center">'
                '<span style="color: #FFFFFF;font-size:15pt;">'
                "{}</span></div>".format("Obstruction detected!")
            )
            self.obstruction_text_item = pg.TextItem(
                html=obstruction_html,
                fill=orange_color,
                anchor=(0.5, 0),
            )
            no_obstruction_html = (
                '<div style="text-align: center">'
                '<span style="color: #FFFFFF;font-size:15pt;">'
                "{}</span></div>".format("No obstruction detected.")
            )
            self.no_obstruction_text_item = pg.TextItem(
                html=no_obstruction_html,
                fill=blue_color,
                anchor=(0.5, 0),
            )

            obs_text_x_pos = (
                min(self.obs_distances) + (max(self.obs_distances) - min(self.obs_distances)) * 0.5
            )
            obs_text_y_pos = MAX_AMPLITUDE * 0.9

            self.obstruction_text_item.setPos(obs_text_x_pos, obs_text_y_pos)
            self.no_obstruction_text_item.setPos(obs_text_x_pos, obs_text_y_pos)

            self.obstruction_plot.addItem(self.obstruction_text_item)
            self.obstruction_plot.addItem(self.no_obstruction_text_item)
            self.obstruction_text_item.hide()
            self.no_obstruction_text_item.hide()

        # Parking info plot.
        self.parking_plot = win.addPlot(row=1, col=0)
        self.parking_plot.setTitle("Noise adjusted amplitude")
        self.parking_plot.setMenuEnabled(False)
        self.parking_plot.showGrid(x=True, y=True)
        self.parking_plot.setLabel("left", "Normalized energy")
        self.parking_plot.setLabel("bottom", "Distance (m)")
        self.parking_plot.addItem(pg.PlotDataItem())
        self.parking_plot.setXRange(min(self.distances), max(self.distances))
        self.parking_plot.setYRange(0, 100)  # Set to standard
        self.parking_plot_curve = self.parking_plot.plot(**self.blue)
        self.parking_smooth_max = et.utils.SmoothMax(self.session_config.update_rate)

    def update_obstruction_text(self) -> None:
        self.obstruction_text_timeout -= 1
        if self.obstruction_text_timeout < 0:
            self.obstruction_text_timeout = 0
            self.obstruction_text_item.hide()

    def show_obstruction_text(self) -> None:
        self.obstruction_text_timeout = 5
        self.obstruction_text_item.show()

    def draw_plot_job(self, *, ref_app_result: RefAppResult) -> None:
        signatures = ref_app_result.extra_result.signature_history
        parking_data = ref_app_result.extra_result.parking_data

        signature_x = [elm[0] for elm in signatures]
        signature_y = [elm[1] for elm in signatures]

        cluster_start = ref_app_result.extra_result.closest_object_dist
        cluster_end = cluster_start + self.cluster_width
        self.sig_plot_curve.setData(x=signature_x, y=signature_y)
        self.sig_plot_cluster_start.setPos(cluster_start)
        self.sig_plot_cluster_end.setPos(cluster_end)
        self.sig_plot_cluster_start.setVisible(False)
        self.sig_plot_cluster_end.setVisible(False)

        sig_max = self.sig_plot_smooth_max.update(max(signature_y))
        self.sig_plot.setYRange(0, sig_max)

        sig_text_x_pos = (
            self.sig_plot_x_range[0] + (self.sig_plot_x_range[1] - self.sig_plot_x_range[0]) * 0.5
        )
        sig_text_y_pos = sig_max * 0.9

        self.parking_car_text_item.setPos(sig_text_x_pos, sig_text_y_pos)
        self.parking_no_car_text_item.setPos(sig_text_x_pos, sig_text_y_pos)

        if ref_app_result.car_detected:
            self.parking_no_car_text_item.hide()
            self.parking_car_text_item.show()
            self.sig_plot_cluster_start.setVisible(True)
            self.sig_plot_cluster_end.setVisible(True)
        else:
            self.parking_car_text_item.hide()
            self.parking_no_car_text_item.show()

        if self.ref_app_config.obstruction_detection:
            obstruction_data = ref_app_result.extra_result.obstruction_data
            self.obstruction_plot_curve.setData(self.obs_distances, obstruction_data)
            point_x, point_y = ref_app_result.extra_result.obstruction_signature
            center_x, center_y = ref_app_result.extra_result.obstruction_center
            rect_x = center_x - self.obs_x_thres
            rect_y = center_y - self.obs_y_thres
            rect_w = 2 * self.obs_x_thres
            rect_h = 2 * self.obs_y_thres

            self.obstruction_center_rect.setRect(rect_x, rect_y, rect_w, rect_h)

            self.obstruction_plot_point.setData(x=[point_x], y=[point_y])
            self.obstruction_plot_center.setData(x=[center_x], y=[center_y])

            if ref_app_result.obstruction_detected:
                self.no_obstruction_text_item.hide()
                self.obstruction_text_item.show()
            else:
                self.obstruction_text_item.hide()
                self.no_obstruction_text_item.show()

        park_max = np.amax(parking_data)
        park_max = self.parking_smooth_max.update(park_max)
        self.parking_plot.setYRange(0, park_max)
        self.parking_plot_curve.setData(self.distances, parking_data)


class ViewPlugin(A121ViewPluginBase):
    TEXT_MSG_MAP = {
        DetailedStatus.OK: "Ready to start.",
        DetailedStatus.CALIBRATION_MISSING: "Run detector calibration.",
        DetailedStatus.CONFIG_MISMATCH: (
            "Current configuration does not match the configuration "
            + "used during detector calibration. Run detector calibration."
        ),
        DetailedStatus.OBSTRUCTION_CALIBRATION_MISSING: "Obstruction calibration missing, run calibration.",
    }

    def __init__(self, app_model: AppModel) -> None:
        super().__init__(app_model=app_model)
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

        self.calibrate_ref_app_button = QPushButton(icons.CALIBRATE(), "Calibrate")
        self.calibrate_ref_app_button.setToolTip(
            "Estimate bg noise and (if applicable) calibrates obstruction detection center.\n\n"
        )
        self.calibrate_ref_app_button.clicked.connect(self._on_calibrate_detector)

        self.message_box = QLabel(self.sticky_widget)
        self.message_box.setWordWrap(True)

        button_group = GroupBox.grid("Controls", parent=self.sticky_widget)
        button_group.layout().addWidget(self.start_button, 0, 0)
        button_group.layout().addWidget(self.stop_button, 0, 1)
        button_group.layout().addWidget(self.calibrate_ref_app_button, 1, 0, 1, -1)
        button_group.layout().addWidget(self.message_box, 2, 0, 1, -1)

        sticky_layout.addWidget(button_group)

        self.misc_error_view = MiscErrorView(self.scrolly_widget)
        scrolly_layout.addWidget(self.misc_error_view)

        sensor_selection_group = GroupBox.vertical("Sensor selection", parent=self.scrolly_widget)
        self.sensor_id_pidget = pidgets.SensorIdPidgetFactory(items=[]).create(
            parent=sensor_selection_group
        )
        self.sensor_id_pidget.sig_update.connect(self._on_sensor_id_update)
        sensor_selection_group.layout().addWidget(self.sensor_id_pidget)
        scrolly_layout.addWidget(sensor_selection_group)

        self.parking_config_editor = AttrsConfigEditor(
            config_type=RefAppConfig,
            title="Parking configuration parameters",
            factory_mapping=self._get_parking_pidget_mapping(),
            parent=self.scrolly_widget,
        )
        self.parking_config_editor.sig_update.connect(self._on_parking_config_update)
        scrolly_layout.addWidget(self.parking_config_editor)

        self.obstruction_config_editor = AttrsConfigEditor(
            config_type=RefAppConfig,
            title="Obstruction configuration parameters",
            factory_mapping=self._get_obstruction_pidget_mapping(),
            parent=self.scrolly_widget,
        )
        self.obstruction_config_editor.sig_update.connect(self._on_obstruction_config_update)
        scrolly_layout.addWidget(self.obstruction_config_editor)

        self.sensor_config_editor = AttrsConfigEditor(
            config_type=RefAppConfig,
            title="Sensor configuration",
            factory_mapping=self._get_sensor_config_pidget_mapping(),
            parent=self.scrolly_widget,
        )
        self.sensor_config_editor.sig_update.connect(self._on_config_update)
        scrolly_layout.addWidget(self.sensor_config_editor)

        self.sticky_widget.setLayout(sticky_layout)
        self.scrolly_widget.setLayout(scrolly_layout)

    @classmethod
    def _get_sensor_config_pidget_mapping(cls) -> PidgetGroupFactoryMapping:
        return {
            pidgets.FlatPidgetGroup(): {
                "update_rate": pidgets.FloatPidgetFactory(
                    name_label_text="Update rate:",
                    name_label_tooltip=get_attribute_docstring(RefAppConfig, "update_rate"),
                    suffix=" Hz",
                    decimals=1,
                ),
                "hwaas": pidgets.IntPidgetFactory(
                    name_label_text="HWAAS:",
                    name_label_tooltip=get_attribute_docstring(RefAppConfig, "hwaas"),
                    limits=(1, 511),
                ),
                "profile": pidgets.EnumPidgetFactory(
                    name_label_text="Profile:",
                    name_label_tooltip=get_attribute_docstring(RefAppConfig, "profile"),
                    enum_type=a121.Profile,
                    label_mapping={
                        a121.Profile.PROFILE_1: "1 (shortest)",
                        a121.Profile.PROFILE_2: "2",
                        a121.Profile.PROFILE_3: "3",
                        a121.Profile.PROFILE_4: "4",
                        a121.Profile.PROFILE_5: "5 (longest)",
                    },
                ),
            }
        }

    @classmethod
    def _get_parking_pidget_mapping(cls) -> PidgetGroupFactoryMapping:
        return {
            pidgets.FlatPidgetGroup(): {
                "range_start_m": pidgets.FloatPidgetFactory(
                    name_label_text="Range start:",
                    name_label_tooltip=get_attribute_docstring(RefAppConfig, "range_start_m"),
                    suffix=" m",
                    limits=(0.08, None),
                    decimals=2,
                ),
                "range_end_m": pidgets.FloatPidgetFactory(
                    name_label_text="Range end:",
                    name_label_tooltip=get_attribute_docstring(RefAppConfig, "range_end_m"),
                    suffix=" m",
                    limits=(0.1, None),
                    decimals=2,
                ),
                "queue_length_n": pidgets.IntPidgetFactory(
                    name_label_text="Queue length:",
                    name_label_tooltip=get_attribute_docstring(RefAppConfig, "queue_length_n"),
                    limits=(1, 200),
                ),
                "amplitude_threshold": pidgets.FloatSliderPidgetFactory(
                    name_label_text="Amplitude threshold:",
                    name_label_tooltip=get_attribute_docstring(
                        RefAppConfig, "amplitude_threshold"
                    ),
                    limits=(1.0, 20.0),
                    decimals=1,
                ),
                "weighted_distance_threshold_m": pidgets.FloatPidgetFactory(
                    name_label_text="Weighted distance threshold:",
                    name_label_tooltip=get_attribute_docstring(
                        RefAppConfig, "weighted_distance_threshold_m"
                    ),
                    suffix=" m",
                    limits=(0.0, None),
                    decimals=2,
                ),
                "signature_similarity_threshold": pidgets.FloatSliderPidgetFactory(
                    name_label_text="Signature similarity threshold:",
                    name_label_tooltip=get_attribute_docstring(
                        RefAppConfig, "signature_similarity_threshold"
                    ),
                    suffix=" %",
                    limits=(0, 100.0),
                    decimals=1,
                ),
                "obstruction_detection": pidgets.CheckboxPidgetFactory(
                    name_label_text="Enable obstruction detection",
                    name_label_tooltip=get_attribute_docstring(
                        RefAppConfig, "obstruction_detection"
                    ),
                ),
            }
        }

    @classmethod
    def _get_obstruction_pidget_mapping(cls) -> PidgetGroupFactoryMapping:
        return {
            pidgets.FlatPidgetGroup(): {
                "obstruction_distance_threshold": pidgets.FloatSliderPidgetFactory(
                    name_label_text="Obstruction distance threshold:",
                    name_label_tooltip=get_attribute_docstring(
                        RefAppConfig, "obstruction_distance_threhsold"
                    ),
                    limits=(0.001, 1.0),
                    decimals=3,
                    log_scale=True,
                ),
                "obstruction_start_m": pidgets.FloatPidgetFactory(
                    name_label_text="Range start:",
                    name_label_tooltip=get_attribute_docstring(
                        RefAppConfig, "obstruction_start_m"
                    ),
                    suffix=" m",
                    limits=(0.01, None),
                    decimals=2,
                ),
                "obstruction_end_m": pidgets.FloatPidgetFactory(
                    name_label_text="Range end:",
                    name_label_tooltip=get_attribute_docstring(RefAppConfig, "obstruction_end_m"),
                    suffix=" m",
                    limits=(0.01, None),
                    decimals=2,
                ),
            }
        }

    def on_backend_state_update(self, state: Optional[SharedState]) -> None:
        if state is None:
            self.sensor_config_editor.set_data(None)
            self.parking_config_editor.set_data(None)
            self.obstruction_config_editor.set_data(None)
            self.message_box.setText("")
        else:
            self.sensor_id_pidget.set_data(state.sensor_id)
            self.sensor_config_editor.set_data(state.config)
            self.parking_config_editor.set_data(state.config)
            self.obstruction_config_editor.set_data(state.config)

            if state.config is not None and state.context is not None:
                status = RefApp.get_ref_app_status(state.config, state.context)
                self.message_box.setText(self.TEXT_MSG_MAP[status.ref_app_state])
            else:
                self.message_box.setText("")

            results = state.config._collect_validation_results()

            not_handled = self.parking_config_editor.handle_validation_results(results)

            not_handled = self.misc_error_view.handle_validation_results(not_handled)

            assert not_handled == []

    def on_app_model_update(self, app_model: AppModel) -> None:
        main_enable = app_model.plugin_state == PluginState.LOADED_IDLE
        state = app_model.backend_plugin_state

        if state is None:
            ref_app_ready = False
            obs_enable = True
        else:
            obs_enable = state.config.obstruction_detection

            if state.context is not None and state.config is not None:
                status = RefApp.get_ref_app_status(state.config, state.context)
                ref_app_ready = status.ready_to_start
            else:
                ref_app_ready = False

        self.sensor_config_editor.setEnabled(main_enable)
        self.parking_config_editor.setEnabled(main_enable)
        self.obstruction_config_editor.setEnabled(main_enable and obs_enable)

        self.sensor_id_pidget.set_selectable_sensors(app_model.connected_sensors)

        self.calibrate_ref_app_button.setEnabled(
            visual_policies.start_button_enabled(app_model),
        )

        self.start_button.setEnabled(
            visual_policies.start_button_enabled(
                app_model,
                extra_condition=(self.sensor_config_editor.is_ready and ref_app_ready),
            )
        )
        self.stop_button.setEnabled(visual_policies.stop_button_enabled(app_model))

    def _on_config_update(self, config: RefAppConfig) -> None:
        BackendPlugin.update_config.rpc(self.app_model.put_task, config=config)

    def _on_calibrate_detector(self) -> None:
        BackendPlugin.calibrate_detector.rpc(self.app_model.put_task)

    def _on_parking_config_update(self, parking_config: RefAppConfig) -> None:
        config = self.parking_config_editor.get_data()
        assert config is not None
        BackendPlugin.update_config.rpc(self.app_model.put_task, config=config)

    def _on_obstruction_config_update(self, parking_config: RefAppConfig) -> None:
        config = self.obstruction_config_editor.get_data()
        assert config is not None
        BackendPlugin.update_config.rpc(self.app_model.put_task, config=config)

    def _send_defaults_request(self) -> None:
        BackendPlugin.restore_defaults.rpc(self.app_model.put_task)

    def _on_sensor_id_update(self, sensor_id: int) -> None:
        BackendPlugin.update_sensor_id.rpc(self.app_model.put_task, sensor_id=sensor_id)


class PluginSpec(PluginSpecBase):
    def create_backend_plugin(
        self, callback: Callable[[Message], None], key: str
    ) -> BackendPlugin:
        return BackendPlugin(callback=callback, generation=self.generation, key=key)

    def create_view_plugin(self, app_model: AppModel) -> ViewPlugin:
        return ViewPlugin(app_model=app_model)

    def create_plot_plugin(self, app_model: AppModel) -> PlotPlugin:
        return PlotPlugin(app_model=app_model)


PARKING_PLUGIN = PluginSpec(
    generation=PluginGeneration.A121,
    key="parking",
    title="Parking",
    docs_link="https://docs.acconeer.com/en/latest/ref_apps/a121/parking.html",
    description="Detect parked cars.",
    family=PluginFamily.REF_APP,
    presets=[
        PluginPresetBase(
            name="Ground",
            description="Ground mounted",
            preset_id=PluginPresetId.GROUND,
        ),
        PluginPresetBase(
            name="Pole",
            description="Pole mounted",
            preset_id=PluginPresetId.POLE,
        ),
    ],
    default_preset_id=PluginPresetId.GROUND,
)
