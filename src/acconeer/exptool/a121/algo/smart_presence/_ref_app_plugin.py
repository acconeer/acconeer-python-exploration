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

from PySide6 import QtCore
from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121._h5_utils import _create_h5_string_dataset
from acconeer.exptool.a121.algo._base import AlgoBase
from acconeer.exptool.a121.algo._plugins import (
    DetectorBackendPluginBase,
    DetectorPlotPluginBase,
    DetectorViewPluginBase,
)
from acconeer.exptool.a121.algo.presence._detector import Detector
from acconeer.exptool.a121.algo.presence._detector_plugin import ViewPlugin as PresenceViewPlugin
from acconeer.exptool.app.new import (
    BUTTON_ICON_COLOR,
    AppModel,
    AttrsConfigEditor,
    BackendLogger,
    GeneralMessage,
    GridGroupBox,
    Message,
    MiscErrorView,
    PidgetGroupFactoryMapping,
    PluginFamily,
    PluginGeneration,
    PluginPresetBase,
    PluginSpecBase,
    PluginState,
    VerticalGroupBox,
    is_task,
    pidgets,
)

from ._configs import get_long_range_config, get_medium_range_config, get_short_range_config
from ._ref_app import RefApp, RefAppConfig, RefAppResult, _load_algo_data


@attrs.mutable(kw_only=True)
class PlotConfig(AlgoBase):
    show_all_detected_zones: bool = attrs.field(default=False)


@attrs.mutable(kw_only=True)
class SharedState:
    sensor_id: int = attrs.field(default=1)
    config: RefAppConfig = attrs.field(factory=RefAppConfig)
    plot_config: PlotConfig = attrs.field(factory=PlotConfig)


class PluginPresetId(Enum):
    SHORT_RANGE = auto()
    MEDIUM_RANGE = auto()
    LONG_RANGE = auto()


class BackendPlugin(DetectorBackendPluginBase[SharedState]):

    PLUGIN_PRESETS: Mapping[int, Callable[[], RefAppConfig]] = {
        PluginPresetId.SHORT_RANGE.value: lambda: get_short_range_config(),
        PluginPresetId.MEDIUM_RANGE.value: lambda: get_medium_range_config(),
        PluginPresetId.LONG_RANGE.value: lambda: get_long_range_config(),
    }

    def __init__(
        self, callback: Callable[[Message], None], generation: PluginGeneration, key: str
    ) -> None:
        super().__init__(callback=callback, generation=generation, key=key)

        self._recorder: Optional[a121.H5Recorder] = None
        self._ref_app_instance: Optional[RefApp] = None
        self._log = BackendLogger.getLogger(__name__)

        self.restore_defaults()

    def _load_from_cache(self, file: h5py.File) -> None:
        self.shared_state.config = RefAppConfig.from_json(file["config"][()])
        self.shared_state.plot_config = PlotConfig.from_json(file["plot_config"][()])

        show_all_detected_zones = self.shared_state.plot_config.show_all_detected_zones
        self.shared_state.config.show_all_detected_zones = show_all_detected_zones

    @is_task
    def restore_defaults(self) -> None:
        self.shared_state = SharedState()
        self.broadcast(sync=True)

    @is_task
    def update_sensor_id(self, *, sensor_id: int) -> None:
        self.shared_state.sensor_id = sensor_id
        self.broadcast(sync=True)

    @is_task
    def update_plot_config(self, *, config: PlotConfig) -> None:
        self.shared_state.plot_config = config
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

    def save_to_cache(self, file: h5py.File) -> None:
        _create_h5_string_dataset(file, "config", self.shared_state.config.to_json())
        _create_h5_string_dataset(file, "plot_config", self.shared_state.plot_config.to_json())

    @is_task
    def set_preset(self, preset_id: int) -> None:
        preset_config = self.PLUGIN_PRESETS[preset_id]
        self.shared_state.config = preset_config()
        self.shared_state.plot_config = PlotConfig()
        self.broadcast(sync=True)

    def load_from_record_setup(self, *, record: a121.H5Record) -> None:
        algo_group = record.get_algo_group(self.key)
        _, config = _load_algo_data(algo_group)
        self.shared_state.config = config
        self.shared_state.sensor_id = record.sensor_id

    def _start_session(self, recorder: Optional[a121.H5Recorder]) -> None:
        assert self.client
        self._ref_app_instance = RefApp(
            client=self.client,
            sensor_id=self.shared_state.sensor_id,
            ref_app_config=self.shared_state.config,
        )
        self._ref_app_instance.start(recorder)
        self.callback(
            GeneralMessage(
                name="setup",
                kwargs=dict(
                    ref_app_config=self.shared_state.config,
                    sensor_config=Detector._get_sensor_config(
                        self._ref_app_instance.detector.config
                    ),
                    plot_config=self.shared_state.plot_config,
                    estimated_frame_rate=self._ref_app_instance.detector.estimated_frame_rate,
                ),
                recipient="plot_plugin",
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

        self.callback(GeneralMessage(name="plot", data=result, recipient="plot_plugin"))


class PlotPlugin(DetectorPlotPluginBase):
    def __init__(self, *, plot_layout: pg.GraphicsLayout, app_model: AppModel) -> None:
        super().__init__(plot_layout=plot_layout, app_model=app_model)

    def setup_from_message(self, message: GeneralMessage) -> None:
        assert message.kwargs is not None
        self.setup(**message.kwargs)

    def update_from_message(self, message: GeneralMessage) -> None:
        assert isinstance(message.data, RefAppResult)
        self.update(message.data)

    def setup(
        self,
        ref_app_config: RefAppConfig,
        sensor_config: a121.SensorConfig,
        plot_config: PlotConfig,
        estimated_frame_rate: float,
    ) -> None:
        self.ref_app_config = ref_app_config
        self.distances = np.linspace(
            ref_app_config.start_m, ref_app_config.end_m, sensor_config.num_points
        )

        self.show_all_detected_zones = plot_config.show_all_detected_zones

        self.history_length_s = 5
        self.history_length_n = int(round(self.history_length_s * estimated_frame_rate))
        self.intra_history = np.zeros(self.history_length_n)
        self.inter_history = np.zeros(self.history_length_n)

        self.num_sectors = min(ref_app_config.num_zones, self.distances.size)
        self.sector_size = max(1, -(-self.distances.size // self.num_sectors))

        self.sector_offset = (self.num_sectors * self.sector_size - self.distances.size) // 2
        win = self.plot_layout

        self.intra_limit_lines = []
        self.inter_limit_lines = []

        # Intra presence history plot

        self.intra_hist_plot = win.addPlot(
            row=0,
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
        self.intra_history_smooth_max = et.utils.SmoothMax(estimated_frame_rate)
        self.intra_hist_plot.setYRange(0, 10)
        if not self.ref_app_config.intra_enable:
            intra_color = et.utils.color_cycler(1)
            intra_color = f"{intra_color}50"
            intra_dashed_pen = pg.mkPen(intra_color, width=2.5, style=QtCore.Qt.DashLine)
            intra_pen = pg.mkPen(intra_color, width=2)
        else:
            intra_dashed_pen = et.utils.pg_pen_cycler(1, width=2.5, style="--")
            intra_pen = et.utils.pg_pen_cycler(1)

        self.intra_hist_curve = self.intra_hist_plot.plot(pen=intra_pen)
        limit_line = pg.InfiniteLine(angle=0, pen=intra_dashed_pen)
        self.intra_hist_plot.addItem(limit_line)
        self.intra_limit_lines.append(limit_line)

        for line in self.intra_limit_lines:
            line.setPos(self.ref_app_config.intra_detection_threshold)

        # Inter presence history plot

        self.inter_hist_plot = win.addPlot(
            row=0,
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
        self.inter_history_smooth_max = et.utils.SmoothMax(estimated_frame_rate)
        self.inter_hist_plot.setYRange(0, 10)
        if not self.ref_app_config.inter_enable:
            inter_color = et.utils.color_cycler(0)
            inter_color = f"{inter_color}50"
            inter_dashed_pen = pg.mkPen(inter_color, width=2.5, style=QtCore.Qt.DashLine)
            inter_pen = pg.mkPen(inter_color, width=2)
        else:
            inter_pen = et.utils.pg_pen_cycler(0)
            inter_dashed_pen = et.utils.pg_pen_cycler(0, width=2.5, style="--")

        self.inter_hist_curve = self.inter_hist_plot.plot(pen=inter_pen)
        limit_line = pg.InfiniteLine(angle=0, pen=inter_dashed_pen)
        self.inter_hist_plot.addItem(limit_line)
        self.inter_limit_lines.append(limit_line)

        for line in self.inter_limit_lines:
            line.setPos(self.ref_app_config.inter_detection_threshold)

        # Sector plot

        self.sector_plot = pg.PlotItem(
            title="Detection zone<br>Detection type: fast (orange), slow (blue), both (green)"
        )
        self.sector_plot.setAspectLocked()
        self.sector_plot.hideAxis("left")
        self.sector_plot.hideAxis("bottom")
        self.sectors = []
        self.limit_text = []

        self.range_html = (
            '<div style="text-align: center">'
            '<span style="color: #000000;font-size:12pt;">'
            "{}</span></div>"
        )

        pen = pg.mkPen("k", width=1)
        span_deg = 25
        for r in np.flip(np.arange(self.num_sectors) + 1):
            sector = pg.QtWidgets.QGraphicsEllipseItem(-r, -r, r * 2, r * 2)
            sector.setStartAngle(-16 * span_deg)
            sector.setSpanAngle(16 * span_deg * 2)
            sector.setPen(pen)
            self.sector_plot.addItem(sector)
            self.sectors.append(sector)

            limit = pg.TextItem(html=self.range_html, anchor=(0.5, 0.5), angle=25)
            x = r * np.cos(np.radians(span_deg))
            y = r * np.sin(np.radians(span_deg))
            limit.setPos(x, y + 0.25)
            self.sector_plot.addItem(limit)
            self.limit_text.append(limit)

        self.sectors.reverse()

        start_limit_text = pg.TextItem(html=self.range_html, anchor=(0.5, 0.5), angle=25)
        range_html = self.range_html.format(f"{ref_app_config.start_m}")
        start_limit_text.setHtml(range_html)
        start_limit_text.setPos(0, 0.25)
        self.sector_plot.addItem(start_limit_text)

        unit_text = pg.TextItem(html=self.range_html, anchor=(0.5, 0.5))
        unit_html = self.range_html.format("[m]")
        unit_text.setHtml(unit_html)
        unit_text.setPos(
            self.num_sectors + 0.5, (self.num_sectors + 1) * np.sin(np.radians(span_deg))
        )
        self.sector_plot.addItem(unit_text)

        sublayout = win.addLayout(row=1, col=0, colspan=2)
        sublayout.layout.setColumnStretchFactor(0, 2)
        sublayout.addItem(self.sector_plot, row=0, col=0)

    def update(self, data: RefAppResult) -> None:

        # Intra presence

        move_hist_xs = np.linspace(-self.history_length_s, 0, self.history_length_n)

        self.intra_history = np.roll(self.intra_history, -1)
        self.intra_history[-1] = data.intra_presence_score

        m_hist = max(
            float(np.max(self.intra_history)), self.ref_app_config.intra_detection_threshold * 1.05
        )
        m_hist = self.intra_history_smooth_max.update(m_hist)

        self.intra_hist_plot.setYRange(0, m_hist)
        self.intra_hist_curve.setData(move_hist_xs, self.intra_history)

        # Inter presence

        self.inter_history = np.roll(self.inter_history, -1)
        self.inter_history[-1] = data.inter_presence_score

        m_hist = max(
            float(np.max(self.inter_history)), self.ref_app_config.inter_detection_threshold * 1.05
        )
        m_hist = self.inter_history_smooth_max.update(m_hist)

        self.inter_hist_plot.setYRange(0, m_hist)
        self.inter_hist_curve.setData(move_hist_xs, self.inter_history)

        # Sector

        brush = et.utils.pg_brush_cycler(7)
        for sector in self.sectors:
            sector.setBrush(brush)

        if data.presence_detected:
            if self.show_all_detected_zones:
                for zone, (inter_value, intra_value) in enumerate(
                    zip(data.inter_zone_detections, data.intra_zone_detections)
                ):
                    if inter_value + intra_value == 2:
                        self.sectors[zone].setBrush(et.utils.pg_brush_cycler(2))
                    elif inter_value == 1:
                        self.sectors[zone].setBrush(et.utils.pg_brush_cycler(0))
                    elif intra_value == 1:
                        self.sectors[zone].setBrush(et.utils.pg_brush_cycler(1))
            else:
                assert data.max_presence_zone is not None
                if data.max_presence_zone == data.max_intra_zone:
                    self.sectors[data.max_presence_zone].setBrush(et.utils.pg_brush_cycler(1))
                else:
                    self.sectors[data.max_presence_zone].setBrush(et.utils.pg_brush_cycler(0))

        for (text_item, limit) in zip(self.limit_text, np.flip(data.zone_limits)):
            range_html = self.range_html.format(np.around(limit, 1))
            text_item.setHtml(range_html)


class ViewPlugin(DetectorViewPluginBase):
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

        button_group = GridGroupBox("Controls", parent=self.sticky_widget)
        button_group.layout().addWidget(self.start_button, 0, 0)
        button_group.layout().addWidget(self.stop_button, 0, 1)

        sticky_layout.addWidget(button_group)

        self.misc_error_view = MiscErrorView(self.scrolly_widget)
        scrolly_layout.addWidget(self.misc_error_view)

        sensor_selection_group = VerticalGroupBox("Sensor selection", parent=self.scrolly_widget)
        self.sensor_id_pidget = pidgets.SensorIdPidgetFactory(items=[]).create(
            parent=sensor_selection_group
        )
        self.sensor_id_pidget.sig_parameter_changed.connect(self._on_sensor_id_update)
        sensor_selection_group.layout().addWidget(self.sensor_id_pidget)
        scrolly_layout.addWidget(sensor_selection_group)

        self.config_editor = AttrsConfigEditor[RefAppConfig](
            title="Ref App parameters",
            factory_mapping=self._get_pidget_mapping(),
            parent=self.scrolly_widget,
        )
        self.config_editor.sig_update.connect(self._on_config_update)
        scrolly_layout.addWidget(self.config_editor)

        self.plot_config_editor = AttrsConfigEditor[PlotConfig](
            title="Plot parameters",
            factory_mapping={
                "show_all_detected_zones": pidgets.CheckboxPidgetFactory(
                    name_label_text="Show all detected zones",
                )
            },
            parent=self.scrolly_widget,
        )
        self.plot_config_editor.sig_update.connect(self._on_plot_config_update)
        scrolly_layout.addWidget(self.plot_config_editor)

        self.sticky_widget.setLayout(sticky_layout)
        self.scrolly_widget.setLayout(scrolly_layout)

    @classmethod
    def _get_pidget_mapping(cls) -> PidgetGroupFactoryMapping:
        presence_pidget_mapping = dict(PresenceViewPlugin._get_pidget_mapping())
        presence_pidget_mapping.update(
            {
                pidgets.FlatPidgetGroup(): {
                    "num_zones": pidgets.IntPidgetFactory(
                        name_label_text="Number of zones",
                        limits=(1, None),
                    ),
                }
            }
        )
        return presence_pidget_mapping

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
            self.stop_button.setEnabled(False)

            self.config_editor.set_data(None)
            self.config_editor.setEnabled(False)
            self.sensor_id_pidget.set_selected_sensor(None, [])

            return

        assert isinstance(state, SharedState)

        self.config_editor.setEnabled(app_model.plugin_state == PluginState.LOADED_IDLE)
        self.config_editor.set_data(state.config)
        self.plot_config_editor.setEnabled(app_model.plugin_state == PluginState.LOADED_IDLE)
        self.plot_config_editor.set_data(state.plot_config)
        self.sensor_id_pidget.set_selected_sensor(state.sensor_id, app_model.connected_sensors)
        self.sensor_id_pidget.setEnabled(app_model.plugin_state.is_steady)

        self.start_button.setEnabled(
            app_model.is_ready_for_session() and self.config_editor.is_ready
        )
        self.stop_button.setEnabled(app_model.plugin_state == PluginState.LOADED_BUSY)

    def _on_config_update(self, config: RefAppConfig) -> None:
        self.app_model.put_backend_plugin_task("update_config", {"config": config})

    def _on_plot_config_update(self, config: PlotConfig) -> None:
        self.app_model.put_backend_plugin_task("update_plot_config", {"config": config})

    def handle_message(self, message: GeneralMessage) -> None:
        if message.name == "sync":
            self._log.debug(f"{type(self).__name__} syncing")

            self.config_editor.sync()
            self.plot_config_editor.sync()
        else:
            raise RuntimeError("Unknown message")

    def _send_defaults_request(self) -> None:
        self.app_model.put_backend_plugin_task("restore_defaults")

    def _on_sensor_id_update(self, sensor_id: int) -> None:
        self.app_model.put_backend_plugin_task("update_sensor_id", {"sensor_id": sensor_id})


class PluginSpec(PluginSpecBase):
    def create_backend_plugin(
        self, callback: Callable[[Message], None], key: str
    ) -> BackendPlugin:
        return BackendPlugin(callback=callback, generation=self.generation, key=key)

    def create_view_plugin(self, app_model: AppModel, view_widget: QWidget) -> ViewPlugin:
        return ViewPlugin(app_model=app_model, view_widget=view_widget)

    def create_plot_plugin(
        self, app_model: AppModel, plot_layout: pg.GraphicsLayout
    ) -> PlotPlugin:
        return PlotPlugin(app_model=app_model, plot_layout=plot_layout)


SMART_PRESENCE_PLUGIN = PluginSpec(
    generation=PluginGeneration.A121,
    key="smart_presence",
    title="Smart presence",
    description="Split presence detection range into zones.",
    family=PluginFamily.REF_APP,
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
    ],
    default_preset_id=PluginPresetId.MEDIUM_RANGE,
)
