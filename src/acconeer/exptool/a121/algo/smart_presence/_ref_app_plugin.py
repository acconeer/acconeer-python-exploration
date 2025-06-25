# Copyright (c) Acconeer AB, 2023-2025
# All rights reserved

from __future__ import annotations

import logging
from enum import Enum, auto
from typing import Callable, List, Mapping, Optional, Tuple

import attrs
import h5py
import numpy as np
import numpy.typing as npt

from PySide6 import QtCore
from PySide6.QtWidgets import QPushButton, QVBoxLayout

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool._core.docstrings import get_attribute_docstring
from acconeer.exptool.a121._h5_utils import _create_h5_string_dataset
from acconeer.exptool.a121.algo._plugins import (
    A121BackendPluginBase,
    A121ViewPluginBase,
)
from acconeer.exptool.a121.algo.presence._detector import Detector
from acconeer.exptool.a121.algo.presence._detector_plugin import ViewPlugin as PresenceViewPlugin
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
from acconeer.exptool.app.new.ui.components import CollapsibleWidget
from acconeer.exptool.app.new.ui.components.a121 import (
    SensorConfigEditor,
)

from ._configs import (
    get_ceiling_config,
    get_long_range_config,
    get_low_power_config,
    get_medium_range_config,
    get_short_range_config,
)
from ._ref_app import (
    PresenceWakeUpConfig,
    PresenceZoneConfig,
    RefApp,
    RefAppConfig,
    RefAppContext,
    RefAppResult,
    _load_algo_data,
    _Mode,
)


log = logging.getLogger(__name__)


@attrs.mutable(kw_only=True)
class SharedState:
    sensor_id: int = attrs.field(default=1)
    config: RefAppConfig = attrs.field(factory=get_medium_range_config)
    ref_app_context: Optional[RefAppContext] = attrs.field(default=None)


class PluginPresetId(Enum):
    SHORT_RANGE = auto()
    MEDIUM_RANGE = auto()
    LONG_RANGE = auto()
    CEILING = auto()
    LOW_POWER = auto()


@attrs.frozen(kw_only=True)
class SetupMessage(GeneralMessage):
    ref_app_config: RefAppConfig
    estimated_frame_rate: float
    nominal_zone_limits: npt.NDArray[np.float64]
    wake_up_zone_limits: npt.NDArray[np.float64]
    name: str = attrs.field(default="setup", init=False)
    recipient: backend.RecipientLiteral = attrs.field(default="plot_plugin", init=False)


class BackendPlugin(A121BackendPluginBase[SharedState]):
    PLUGIN_PRESETS: Mapping[int, Callable[[], RefAppConfig]] = {
        PluginPresetId.SHORT_RANGE.value: lambda: get_short_range_config(),
        PluginPresetId.MEDIUM_RANGE.value: lambda: get_medium_range_config(),
        PluginPresetId.LONG_RANGE.value: lambda: get_long_range_config(),
        PluginPresetId.CEILING.value: lambda: get_ceiling_config(),
        PluginPresetId.LOW_POWER.value: lambda: get_low_power_config(),
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

    @is_task
    def update_nominal_config(self, *, config: PresenceZoneConfig) -> None:
        self.shared_state.config.nominal_config = config
        self.broadcast()

    @is_task
    def update_wake_up_config(self, *, config: PresenceWakeUpConfig) -> None:
        self.shared_state.config.wake_up_config = config
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
        _, config, ref_app_context = _load_algo_data(algo_group)
        self.shared_state.config = config
        self.shared_state.ref_app_context = ref_app_context
        self.shared_state.sensor_id = record.session(0).sensor_id

    def _start_session(self, recorder: Optional[a121.H5Recorder]) -> None:
        assert self.client
        self._ref_app_instance = RefApp(
            client=self.client,
            sensor_id=self.shared_state.sensor_id,
            ref_app_config=self.shared_state.config,
            ref_app_context=self.shared_state.ref_app_context,
        )

        self._ref_app_instance.start(recorder)

        nominal_sensor_config = Detector._get_sensor_config(
            self._ref_app_instance.nominal_detector_config
        )
        distances = np.linspace(
            self.shared_state.config.nominal_config.start_m,
            self.shared_state.config.nominal_config.end_m,
            sum([subsweep.num_points for subsweep in nominal_sensor_config.subsweeps]),
        )
        nominal_zone_limits = self._ref_app_instance.ref_app_processor.create_zones(
            distances, self.shared_state.config.nominal_config.num_zones
        )

        # self._ref_app_instance.ref_app_processor.zone_limits will always be for
        # wake_up_config if wake_up_mode is enabled
        self.callback(
            SetupMessage(
                ref_app_config=self.shared_state.config,
                estimated_frame_rate=self._ref_app_instance.detector.estimated_frame_rate,
                nominal_zone_limits=nominal_zone_limits,
                wake_up_zone_limits=self._ref_app_instance.ref_app_processor.zone_limits,
            )
        )

    def end_session(self) -> None:
        if self._ref_app_instance is None:
            raise RuntimeError
        if self._recorder is not None:
            self._recorder.close()
        self._ref_app_instance.stop()

    def get_next(self) -> None:
        assert self.client
        if self._ref_app_instance is None:
            raise RuntimeError
        result = self._ref_app_instance.get_next()

        self.callback(backend.PlotMessage(result=result))


class PlotPlugin(PgPlotPlugin):
    def __init__(self, app_model: AppModel) -> None:
        super().__init__(app_model=app_model)
        self._plot_job: Optional[RefAppResult] = None
        self._is_setup = False

    def handle_message(self, message: backend.GeneralMessage) -> None:
        if isinstance(message, backend.PlotMessage):
            self._plot_job = message.result
        elif isinstance(message, SetupMessage):
            self.setup(
                message.ref_app_config,
                message.estimated_frame_rate,
                message.nominal_zone_limits,
                message.wake_up_zone_limits,
            )
            self._is_setup = True
        else:
            log.warn(f"{self.__class__.__name__} got an unsupported command: {message.name!r}.")

    def draw(self) -> None:
        if not self._is_setup or self._plot_job is None:
            return

        try:
            self.draw_plot_job(data=self._plot_job)
        finally:
            self._plot_job = None

    def setup(
        self,
        ref_app_config: RefAppConfig,
        estimated_frame_rate: float,
        nominal_zone_limits: npt.NDArray[np.float64],
        wake_up_zone_limits: npt.NDArray[np.float64],
    ) -> None:
        self.plot_layout.clear()

        self.ref_app_config = ref_app_config
        self.nominal_config = ref_app_config.nominal_config
        self.wake_up_config = ref_app_config.wake_up_config

        self.show_all_detected_zones = self.ref_app_config.show_all_detected_zones

        self.history_length_s = 5
        self.time_fifo: List[float] = []
        self.intra_fifo: List[float] = []
        self.inter_fifo: List[float] = []
        self.switch_data: Optional[RefAppResult] = None
        self.switch_data_sectors: List[pg.QtWidgets.QGraphicsEllipseItem] = []

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
        if not self.nominal_config.intra_enable:
            intra_color = et.utils.color_cycler(1)
            intra_color = f"{intra_color}50"
            self.nominal_intra_dashed_pen = pg.mkPen(
                intra_color, width=2.5, style=QtCore.Qt.PenStyle.DashLine
            )
            self.nominal_intra_pen = pg.mkPen(intra_color, width=2)
        else:
            self.nominal_intra_dashed_pen = et.utils.pg_pen_cycler(1, width=2.5, style="--")
            self.nominal_intra_pen = et.utils.pg_pen_cycler(1)

        self.intra_hist_curve = self.intra_hist_plot.plot(pen=self.nominal_intra_pen)
        limit_line = pg.InfiniteLine(angle=0, pen=self.nominal_intra_dashed_pen)
        self.intra_hist_plot.addItem(limit_line)
        self.intra_limit_lines.append(limit_line)

        for line in self.intra_limit_lines:
            line.setPos(self.nominal_config.intra_detection_threshold)

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
        if not self.nominal_config.inter_enable:
            inter_color = et.utils.color_cycler(0)
            inter_color = f"{inter_color}50"
            self.nominal_inter_dashed_pen = pg.mkPen(
                inter_color, width=2.5, style=QtCore.Qt.PenStyle.DashLine
            )
            self.nominal_inter_pen = pg.mkPen(inter_color, width=2)
        else:
            self.nominal_inter_pen = et.utils.pg_pen_cycler(0)
            self.nominal_inter_dashed_pen = et.utils.pg_pen_cycler(0, width=2.5, style="--")

        self.inter_hist_curve = self.inter_hist_plot.plot(pen=self.nominal_inter_pen)
        limit_line = pg.InfiniteLine(angle=0, pen=self.nominal_inter_dashed_pen)
        self.inter_hist_plot.addItem(limit_line)
        self.inter_limit_lines.append(limit_line)

        for line in self.inter_limit_lines:
            line.setPos(self.nominal_config.inter_detection_threshold)

        # Sector plot

        if ref_app_config.wake_up_mode:
            title = (
                "Nominal config<br>"
                "Detection type: fast (orange), slow (blue), both (green)<br>"
                "Green background indicates active"
            )
        else:
            title = "Nominal config<br>" "Detection type: fast (orange), slow (blue), both (green)"

        self.nominal_sector_plot, self.nominal_sectors = self.create_sector_plot(
            title,
            self.ref_app_config.nominal_config.num_zones,
            self.nominal_config.start_m,
            nominal_zone_limits,
        )

        if not ref_app_config.wake_up_mode:
            sublayout = win.addLayout(row=1, col=0, colspan=2)
            sublayout.layout.setColumnStretchFactor(0, 2)
            sublayout.addItem(self.nominal_sector_plot, row=0, col=0)
        else:
            assert self.wake_up_config is not None
            sublayout = win.addLayout(row=1, col=0, colspan=2)
            sublayout.addItem(self.nominal_sector_plot, row=0, col=1)

            title = (
                "Wake up config<br>"
                "Detection type: fast (orange), slow (blue), both (green),<br>"
                "lingering (light grey)<br>"
                "Green background indicates active"
            )
            self.wake_up_sector_plot, self.wake_up_sectors = self.create_sector_plot(
                title,
                self.wake_up_config.num_zones,
                self.wake_up_config.start_m,
                wake_up_zone_limits,
            )

            sublayout.addItem(self.wake_up_sector_plot, row=0, col=0)

            if self.wake_up_config.intra_enable:
                self.wake_up_intra_dashed_pen = et.utils.pg_pen_cycler(1, width=2.5, style="--")
                self.wake_up_intra_pen = et.utils.pg_pen_cycler(1)
            else:
                intra_color = et.utils.color_cycler(1)
                intra_color = f"{intra_color}50"
                self.wake_up_intra_dashed_pen = pg.mkPen(
                    intra_color, width=2.5, style=QtCore.Qt.PenStyle.DashLine
                )
                self.wake_up_intra_pen = pg.mkPen(intra_color, width=2)

            if self.wake_up_config.inter_enable:
                self.wake_up_inter_pen = et.utils.pg_pen_cycler(0)
                self.wake_up_inter_dashed_pen = et.utils.pg_pen_cycler(0, width=2.5, style="--")
            else:
                inter_color = et.utils.color_cycler(0)
                inter_color = f"{inter_color}50"
                self.wake_up_inter_dashed_pen = pg.mkPen(
                    inter_color, width=2.5, style=QtCore.Qt.PenStyle.DashLine
                )
                self.wake_up_inter_pen = pg.mkPen(inter_color, width=2)

    @staticmethod
    def create_sector_plot(
        title: str, num_sectors: int, start_m: float, zone_limits: npt.NDArray[np.float64]
    ) -> Tuple[pg.PlotItem, List[pg.QtWidgets.QGraphicsEllipseItem]]:
        sector_plot = pg.PlotItem(title=title)

        sector_plot.setAspectLocked()
        sector_plot.hideAxis("left")
        sector_plot.hideAxis("bottom")

        sectors = []
        limit_text = []

        range_html = (
            '<div style="text-align: center">'
            '<span style="color: #000000;font-size:12pt;">'
            "{}</span></div>"
        )

        if start_m == zone_limits[0]:
            x_offset = 0.7
        else:
            x_offset = 0

        pen = pg.mkPen("k", width=1)
        span_deg = 25
        for r in np.flip(np.arange(1, num_sectors + 2)):
            sector = pg.QtWidgets.QGraphicsEllipseItem(-r, -r, r * 2, r * 2)
            sector.setStartAngle(-16 * span_deg)
            sector.setSpanAngle(16 * span_deg * 2)
            sector.setPen(pen)
            sector_plot.addItem(sector)
            sectors.append(sector)

            if r != 1:
                limit = pg.TextItem(html=range_html, anchor=(0.5, 0.5), angle=25)
                x = r * np.cos(np.radians(span_deg))
                y = r * np.sin(np.radians(span_deg))
                limit.setPos(x - x_offset, y + 0.25)
                sector_plot.addItem(limit)
                limit_text.append(limit)

        sectors.reverse()

        if start_m != zone_limits[0]:
            start_limit_text = pg.TextItem(html=range_html, anchor=(0.5, 0.5), angle=25)
            start_range_html = range_html.format(f"{start_m}")
            start_limit_text.setHtml(start_range_html)
            x = 1 * np.cos(np.radians(span_deg))
            y = 1 * np.sin(np.radians(span_deg))

            start_limit_text.setPos(x, y + 0.25)
            sector_plot.addItem(start_limit_text)

        unit_text = pg.TextItem(html=range_html, anchor=(0.5, 0.5))
        unit_html = range_html.format("[m]")
        unit_text.setHtml(unit_html)
        x = (num_sectors + 2) * np.cos(np.radians(span_deg))
        y = (num_sectors + 2) * np.sin(np.radians(span_deg))
        unit_text.setPos(x - x_offset, y + 0.25)
        sector_plot.addItem(unit_text)

        for text_item, limit in zip(limit_text, np.flip(zone_limits)):
            zone_range_html = range_html.format(np.around(limit, 1))
            text_item.setHtml(zone_range_html)

        return sector_plot, sectors

    def draw_plot_job(self, *, data: RefAppResult) -> None:
        if data.used_config == _Mode.NOMINAL_CONFIG:
            inter_threshold = self.nominal_config.inter_detection_threshold
            intra_threshold = self.nominal_config.intra_detection_threshold
            intra_pen = self.nominal_intra_pen
            intra_dashed_pen = self.nominal_intra_dashed_pen
            inter_pen = self.nominal_inter_pen
            inter_dashed_pen = self.nominal_inter_dashed_pen
        else:
            assert self.wake_up_config is not None
            inter_threshold = self.wake_up_config.inter_detection_threshold
            intra_threshold = self.wake_up_config.intra_detection_threshold
            intra_pen = self.wake_up_intra_pen
            intra_dashed_pen = self.wake_up_intra_dashed_pen
            inter_pen = self.wake_up_inter_pen
            inter_dashed_pen = self.wake_up_inter_dashed_pen

        self.time_fifo.append(data.service_result.tick_time)

        if data.switch_delay:
            self.intra_fifo.append(float("nan"))
            self.inter_fifo.append(float("nan"))
        else:
            self.intra_fifo.append(data.intra_presence_score)
            self.inter_fifo.append(data.inter_presence_score)

        while self.time_fifo[-1] - self.time_fifo[0] > self.history_length_s:
            self.time_fifo.pop(0)
            self.intra_fifo.pop(0)
            self.inter_fifo.pop(0)

        times = [t - self.time_fifo[-1] for t in self.time_fifo]

        # Intra presence

        if np.isnan(self.intra_fifo).all():
            m_hist = intra_threshold
        else:
            m_hist = np.maximum(float(np.nanmax(self.intra_fifo)), intra_threshold * 1.05)

        m_hist = self.intra_history_smooth_max.update(m_hist)

        self.intra_hist_plot.setYRange(0, m_hist)
        self.intra_hist_curve.setData(times, self.intra_fifo, connect="finite")
        self.intra_hist_curve.setPen(intra_pen)

        for line in self.intra_limit_lines:
            line.setPos(intra_threshold)
            line.setPen(intra_dashed_pen)

        # Inter presence

        if np.isnan(self.inter_fifo).all():
            m_hist = inter_threshold
        else:
            m_hist = np.maximum(float(np.nanmax(self.inter_fifo)), inter_threshold * 1.05)

        m_hist = self.inter_history_smooth_max.update(m_hist)

        self.inter_hist_plot.setYRange(0, m_hist)
        self.inter_hist_curve.setData(times, self.inter_fifo, connect="finite")
        self.inter_hist_curve.setPen(inter_pen)

        for line in self.inter_limit_lines:
            line.setPos(inter_threshold)
            line.setPen(inter_dashed_pen)

        # Sector

        brush = et.utils.pg_brush_cycler(7)
        for sector in self.nominal_sectors:
            sector.setBrush(brush)

        if not self.ref_app_config.wake_up_mode:
            sectors = self.nominal_sectors[1:]
            show_all_zones = self.show_all_detected_zones
            color_nominal = "white"
        else:
            if data.used_config == _Mode.WAKE_UP_CONFIG:
                sectors = self.wake_up_sectors[1:]
                show_all_zones = True
                color_wake_up = "#DFF1D6"
                color_nominal = "white"
            else:
                sectors = self.nominal_sectors[1:]
                show_all_zones = self.show_all_detected_zones
                color_wake_up = "white"
                color_nominal = "#DFF1D6"

            vb = self.nominal_sector_plot.getViewBox()
            vb.setBackgroundColor(color_nominal)
            vb = self.wake_up_sector_plot.getViewBox()
            vb.setBackgroundColor(color_wake_up)

            for sector in self.wake_up_sectors:
                sector.setBrush(brush)

        if data.presence_detected:
            self.color_zones(data, show_all_zones, sectors)
            self.switch_data = data
            self.switch_data_sectors = sectors
        elif data.switch_delay and self.switch_data is not None:
            self.color_zones(self.switch_data, True, self.switch_data_sectors)

        self.nominal_sectors[0].setPen(pg.mkPen(color_nominal, width=1))
        self.nominal_sectors[0].setBrush(pg.mkBrush(color_nominal))

        if self.ref_app_config.wake_up_mode:
            self.wake_up_sectors[0].setPen(pg.mkPen(color_wake_up, width=1))
            self.wake_up_sectors[0].setBrush(pg.mkBrush(color_wake_up))

    @staticmethod
    def color_zones(
        data: RefAppResult,
        show_all_detected_zones: bool,
        sectors: List[pg.QtWidgets.QGraphicsEllipseItem],
    ) -> None:
        if show_all_detected_zones:
            for zone, (inter_value, intra_value) in enumerate(
                zip(data.inter_zone_detections, data.intra_zone_detections)
            ):
                if inter_value + intra_value == 2:
                    sectors[zone].setBrush(et.utils.pg_brush_cycler(2))
                elif inter_value == 1:
                    sectors[zone].setBrush(et.utils.pg_brush_cycler(0))
                elif intra_value == 1:
                    sectors[zone].setBrush(et.utils.pg_brush_cycler(1))
                elif data.used_config == _Mode.WAKE_UP_CONFIG:
                    assert data.wake_up_detections is not None
                    if data.wake_up_detections[zone] > 0:
                        sectors[zone].setBrush(pg.mkBrush("#b5afa0"))
        else:
            assert data.max_presence_zone is not None
            if data.max_presence_zone == data.max_intra_zone:
                sectors[data.max_presence_zone].setBrush(et.utils.pg_brush_cycler(1))
            else:
                sectors[data.max_presence_zone].setBrush(et.utils.pg_brush_cycler(0))


class ViewPlugin(A121ViewPluginBase):
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

        button_group = GroupBox.grid("Controls", parent=self.sticky_widget)
        button_group.layout().addWidget(self.start_button, 0, 0)
        button_group.layout().addWidget(self.stop_button, 0, 1)

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

        self.config_editor = AttrsConfigEditor(
            title="Ref App parameters",
            factory_mapping={
                "wake_up_mode": pidgets.CheckboxPidgetFactory(
                    name_label_text="Switch config on wake up",
                    name_label_tooltip=get_attribute_docstring(RefAppConfig, "wake_up_mode"),
                ),
                "show_all_detected_zones": pidgets.CheckboxPidgetFactory(
                    name_label_text="Show all detected zones",
                    name_label_tooltip=get_attribute_docstring(
                        RefAppConfig, "show_all_detected_zones"
                    ),
                ),
            },
            config_type=RefAppConfig,
            parent=self.scrolly_widget,
        )
        self.config_editor.sig_update.connect(self._on_config_update)
        scrolly_layout.addWidget(self.config_editor)

        self.subsweep_status_wake_up = SensorConfigEditor()
        self.subsweep_status_wake_up.set_read_only(True)
        wake_up_status_widget = CollapsibleWidget(
            "Wake up subsweep settings",
            self.subsweep_status_wake_up.subsweep_group_box,
            self.scrolly_widget,
        )

        scrolly_layout.addWidget(wake_up_status_widget)

        self.wake_up_config_editor = AttrsConfigEditor(
            title="Wake up config parameters",
            factory_mapping=self._get_presence_wake_up_pidget_mapping(),
            config_type=PresenceWakeUpConfig,
            parent=self.scrolly_widget,
        )
        self.wake_up_config_editor.sig_update.connect(self._on_wake_up_config_update)
        scrolly_layout.addWidget(self.wake_up_config_editor)

        self.subsweep_status_nominal = SensorConfigEditor()
        self.subsweep_status_nominal.set_read_only(True)
        nominal_status_widget = CollapsibleWidget(
            "Nominal subsweep settings",
            self.subsweep_status_nominal.subsweep_group_box,
            self.scrolly_widget,
        )

        scrolly_layout.addWidget(nominal_status_widget)
        self.nominal_config_editor = AttrsConfigEditor(
            title="Nominal config parameters",
            factory_mapping=self._get_presence_zone_pidget_mapping(),
            config_type=PresenceZoneConfig,
            parent=self.scrolly_widget,
        )
        self.nominal_config_editor.sig_update.connect(self._on_nominal_config_update)
        scrolly_layout.addWidget(self.nominal_config_editor)

        self.sticky_widget.setLayout(sticky_layout)
        self.scrolly_widget.setLayout(scrolly_layout)

    @classmethod
    def _get_presence_zone_pidget_mapping(cls) -> PidgetGroupFactoryMapping:
        presence_pidget_mapping = dict(PresenceViewPlugin._get_pidget_mapping())
        presence_pidget_mapping.update(
            {
                pidgets.FlatPidgetGroup(): {
                    "num_zones": pidgets.IntPidgetFactory(
                        name_label_text="Number of zones:",
                        limits=(1, None),
                        name_label_tooltip=get_attribute_docstring(
                            PresenceZoneConfig, "num_zones"
                        ),
                    )
                }
            }
        )
        return presence_pidget_mapping

    @classmethod
    def _get_presence_wake_up_pidget_mapping(cls) -> PidgetGroupFactoryMapping:
        presence_pidget_mapping = dict(cls._get_presence_zone_pidget_mapping())
        presence_pidget_mapping.update(
            {
                pidgets.FlatPidgetGroup(): {
                    "num_zones_for_wake_up": pidgets.IntPidgetFactory(
                        name_label_text="Number zones for wake up:s:",
                        limits=(1, None),
                        name_label_tooltip=get_attribute_docstring(
                            PresenceWakeUpConfig, "num_zones_for_wake_up"
                        ),
                    )
                }
            }
        )
        return presence_pidget_mapping

    def on_backend_state_update(self, state: Optional[SharedState]) -> None:
        if state is None:
            self.config_editor.set_data(None)
            self.nominal_config_editor.set_data(None)
            self.subsweep_status_nominal.set_data(None)
            self.wake_up_config_editor.set_data(None)
            self.subsweep_status_wake_up.set_data(None)
        else:
            self.sensor_id_pidget.set_data(state.sensor_id)
            self.config_editor.set_data(state.config)

            self.nominal_config_editor.set_data(state.config.nominal_config)

            self.wake_up_config_editor.setHidden(not state.config.wake_up_mode)

            if state.config.wake_up_config is not None:
                self.wake_up_config_editor.set_data(state.config.wake_up_config)

            results = state.config._collect_validation_results()

            not_handled = self.config_editor.handle_validation_results(results)

            not_handled = self.wake_up_config_editor.handle_validation_results(not_handled)

            not_handled = self.misc_error_view.handle_validation_results(not_handled)

            assert not_handled == []

            if len(results) == 0:
                self.subsweep_status_nominal.set_data(
                    Detector._get_sensor_config(state.config.nominal_config)
                )
                if state.config.wake_up_config is not None:
                    self.subsweep_status_wake_up.set_data(
                        Detector._get_sensor_config(state.config.wake_up_config)
                    )

    def on_app_model_update(self, app_model: AppModel) -> None:
        self.sensor_id_pidget.set_selectable_sensors(app_model.connected_sensors)

        visual_policies.apply_enabled_policy(
            visual_policies.config_editor_enabled,
            app_model,
            widgets=[
                self.config_editor,
                self.nominal_config_editor,
                self.wake_up_config_editor,
                self.sensor_id_pidget,
            ],
        )

        self.start_button.setEnabled(
            visual_policies.start_button_enabled(
                app_model, extra_condition=self.config_editor.is_ready
            )
        )
        self.stop_button.setEnabled(visual_policies.stop_button_enabled(app_model))

    def _on_config_update(self, config: RefAppConfig) -> None:
        BackendPlugin.update_config.rpc(self.app_model.put_task, config=config)

    def _on_nominal_config_update(self, config: PresenceZoneConfig) -> None:
        BackendPlugin.update_nominal_config.rpc(self.app_model.put_task, config=config)

    def _on_wake_up_config_update(self, config: PresenceWakeUpConfig) -> None:
        BackendPlugin.update_wake_up_config.rpc(self.app_model.put_task, config=config)

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


SMART_PRESENCE_PLUGIN = PluginSpec(
    generation=PluginGeneration.A121,
    key="smart_presence",
    title="Smart presence",
    docs_link="https://docs.acconeer.com/en/latest/ref_apps/a121/smart_presence.html",
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
        PluginPresetBase(
            name="Ceiling",
            description="Ceiling",
            preset_id=PluginPresetId.CEILING,
        ),
        PluginPresetBase(
            name="Low power, Wake up",
            description="Low power, Wake up",
            preset_id=PluginPresetId.LOW_POWER,
        ),
    ],
    default_preset_id=PluginPresetId.MEDIUM_RANGE,
)
