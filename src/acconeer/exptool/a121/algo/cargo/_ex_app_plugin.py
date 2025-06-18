# Copyright (c) Acconeer AB, 2025
# All rights reserved

from __future__ import annotations

import logging
from enum import Enum, auto
from typing import Callable, List, Mapping, Optional

import attrs
import h5py
import numpy as np

from PySide6.QtGui import QFont
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
from acconeer.exptool.a121.algo.distance._detector import ConfigMismatchError
from acconeer.exptool.a121.algo.distance._translation import detector_config_to_session_config
from acconeer.exptool.a121.algo.presence._detector import Detector as PresenceDetector
from acconeer.exptool.app.new import (
    AppModel,
    AttrsConfigEditor,
    BackendLogger,
    GeneralMessage,
    GroupBox,
    Message,
    MiscErrorView,
    PgPlotPlugin,
    PidgetFactoryMapping,
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
    get_10_ft_container_config,
    get_20_ft_container_config,
    get_40_ft_container_config,
    get_no_lens_config,
)
from ._ex_app import (
    PRESENCE_RUN_TIME_S,
    CargoPresenceConfig,
    ContainerSize,
    ExApp,
    ExAppConfig,
    ExAppContext,
    ExAppResult,
    UtilizationLevelConfig,
    _load_algo_data,
    _Mode,
)


log = logging.getLogger(__name__)


@attrs.mutable(kw_only=True)
class SharedState:
    sensor_id: int = attrs.field(default=1)
    config: ExAppConfig = attrs.field(factory=get_20_ft_container_config)
    ex_app_context: Optional[ExAppContext] = attrs.field(default=None)


class PluginPresetId(Enum):
    CONTAINER_10_FT = auto()
    CONTAINER_20_FT = auto()
    CONTAINER_40_FT = auto()
    NO_LENS = auto()


@attrs.frozen(kw_only=True)
class SetupMessage(GeneralMessage):
    ex_app_config: ExAppConfig
    estimated_frame_rate: Optional[float]
    name: str = attrs.field(default="setup", init=False)
    recipient: backend.RecipientLiteral = attrs.field(default="plot_plugin", init=False)


class BackendPlugin(A121BackendPluginBase[SharedState]):
    PLUGIN_PRESETS: Mapping[int, Callable[[], ExAppConfig]] = {
        PluginPresetId.CONTAINER_10_FT.value: lambda: get_10_ft_container_config(),
        PluginPresetId.CONTAINER_20_FT.value: lambda: get_20_ft_container_config(),
        PluginPresetId.CONTAINER_40_FT.value: lambda: get_40_ft_container_config(),
        PluginPresetId.NO_LENS.value: lambda: get_no_lens_config(),
    }

    def __init__(
        self, callback: Callable[[Message], None], generation: PluginGeneration, key: str
    ) -> None:
        super().__init__(callback=callback, generation=generation, key=key, use_app_client=False)

        self._recorder: Optional[a121.H5Recorder] = None
        self._ex_app_instance: Optional[ExApp] = None
        self._log = BackendLogger.getLogger(__name__)
        self._frame_count = 0

        self.restore_defaults()

    def _load_from_cache(self, file: h5py.File) -> None:
        self.shared_state.config = ExAppConfig.from_json(file["config"][()])

    @is_task
    def restore_defaults(self) -> None:
        self.shared_state = SharedState(config=get_no_lens_config())
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
    def update_config(self, *, config: ExAppConfig) -> None:
        self.shared_state.config = config
        self.broadcast()

    @is_task
    def update_utilization_level_config(self, *, config: UtilizationLevelConfig) -> None:
        self.shared_state.config.utilization_level_config = config
        self.broadcast()

    @is_task
    def update_cargo_presence_config(self, *, config: CargoPresenceConfig) -> None:
        self.shared_state.config.cargo_presence_config = config
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
        _, config, ex_app_context = _load_algo_data(algo_group)
        self.shared_state.config = config
        self.shared_state.ex_app_context = ex_app_context
        self.shared_state.sensor_id = record.session(0).sensor_id

    def _start_session(self, recorder: Optional[a121.H5Recorder]) -> None:
        assert self.client

        if (
            self.shared_state.config.cargo_presence_config is not None
            and self.shared_state.ex_app_context is not None
            and self.shared_state.ex_app_context.presence_context is not None
        ):
            update_rate_diff = abs(
                self.shared_state.ex_app_context.presence_context.estimated_frame_rate
                - self.shared_state.config.cargo_presence_config.update_rate
            )
            if update_rate_diff > 0.01:
                self.shared_state.ex_app_context.presence_context = None
                self.send_status_message("Config mismatch, estimating frame rate.")

        try:
            self._ex_app_instance = ExApp(
                client=self.client,
                sensor_id=self.shared_state.sensor_id,
                ex_app_config=self.shared_state.config,
                ex_app_context=self.shared_state.ex_app_context,
            )
            self._ex_app_instance.start(recorder)
        except ConfigMismatchError:
            self._ex_app_instance = ExApp(
                client=self.client,
                sensor_id=self.shared_state.sensor_id,
                ex_app_config=self.shared_state.config,
                ex_app_context=None,
            )
            self.send_status_message("Config mismatch, recalibrating detector.")
            self._ex_app_instance.start(recorder)

        self.shared_state.ex_app_context = self._ex_app_instance.ex_app_context

        if self._ex_app_instance.presence_context is not None:
            estimated_frame_rate = self._ex_app_instance.presence_context.estimated_frame_rate
        else:
            estimated_frame_rate = None

        self.callback(
            SetupMessage(
                ex_app_config=self.shared_state.config,
                estimated_frame_rate=estimated_frame_rate,
            )
        )

    def end_session(self) -> None:
        if self._ex_app_instance is None:
            raise RuntimeError
        if self._recorder is not None:
            self._recorder.close()
        self._ex_app_instance.stop()
        self._frame_count = 0

    def get_next(self) -> None:
        assert self.client
        if self._ex_app_instance is None:
            raise RuntimeError
        result = self._ex_app_instance.get_next()
        self._frame_count += 1

        self.callback(backend.PlotMessage(result=result))
        self.callback(GeneralMessage(name="frame_count", data=self._frame_count))


class PlotPlugin(PgPlotPlugin):
    def __init__(self, app_model: AppModel) -> None:
        super().__init__(app_model=app_model)
        self._plot_jobs: List[ExAppResult] = []
        self._is_setup = False

    def handle_message(self, message: backend.GeneralMessage) -> None:
        if isinstance(message, backend.PlotMessage):
            self._plot_jobs.append(message.result)
        elif isinstance(message, SetupMessage):
            self.setup(
                message.ex_app_config,
                message.estimated_frame_rate,
            )
            self._is_setup = True
        else:
            log.warn(f"{self.__class__.__name__} got an unsupported command: {message.name!r}.")

    def draw(self) -> None:
        if not self._is_setup or self._plot_jobs is None:
            return

        plot_distance = True
        plot_presence = True
        try:
            for plot_job in self._plot_jobs:
                if (plot_job.mode == _Mode.DISTANCE and plot_distance) or (
                    plot_job.mode == _Mode.PRESENCE and plot_presence
                ):
                    self.draw_plot_job(result=plot_job)
        finally:
            self._plot_jobs = []

    def setup(
        self,
        ex_app_config: ExAppConfig,
        estimated_frame_rate: Optional[float],
    ) -> None:
        self.plot_layout.clear()

        self.ex_app_config = ex_app_config
        self.utilization_level_config = ex_app_config.utilization_level_config
        self.cargo_presence_config = ex_app_config.cargo_presence_config

        win = self.plot_layout
        self.num_rects = 16

        # Utilization level

        if self.ex_app_config.activate_utilization_level:
            # Distance sweep plot

            self.sweep_plot = win.addPlot(row=0, col=0, title="Distance sweep")
            self.sweep_plot.setMenuEnabled(False)
            self.sweep_plot.showGrid(x=True, y=True)
            self.sweep_plot.addLegend()
            self.sweep_plot.setLabel("left", "Amplitude")
            self.sweep_plot.setLabel("bottom", "Distance (m)")
            self.sweep_plot.addItem(pg.PlotDataItem())

            self.num_curves = 4

            pen = et.utils.pg_pen_cycler(0)
            brush = et.utils.pg_brush_cycler(0)
            symbol_kw = dict(symbol="o", symbolSize=1, symbolBrush=brush, symbolPen="k")
            feat_kw = dict(pen=pen, **symbol_kw)
            self.sweep_curves = [self.sweep_plot.plot(**feat_kw) for _ in range(self.num_curves)]

            pen = et.utils.pg_pen_cycler(1)
            brush = et.utils.pg_brush_cycler(1)
            symbol_kw = dict(symbol="o", symbolSize=1, symbolBrush=brush, symbolPen="k")
            feat_kw = dict(pen=pen, **symbol_kw)
            self.threshold_curves = [
                self.sweep_plot.plot(**feat_kw) for _ in range(self.num_curves)
            ]

            sweep_plot_legend = pg.LegendItem(offset=(-30, 30))
            sweep_plot_legend.setParentItem(self.sweep_plot.graphicsItem())
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

            self.sweep_smooth_max = et.utils.SmoothMax()

            # Utilization level plot

            self.rect_plot = win.addPlot(row=1, col=0, title="Utilization level")
            self.rect_plot.setAspectLocked()
            self.rect_plot.hideAxis("left")
            self.rect_plot.hideAxis("bottom")
            self.rects = []

            pen = pg.mkPen(None)
            rect_height = self.num_rects / 2.0
            for r in np.arange(self.num_rects) + 1:
                rect = pg.QtWidgets.QGraphicsRectItem(r, rect_height, 1, rect_height)
                rect.setPen(pen)
                rect.setBrush(et.utils.pg_brush_cycler(7))
                self.rect_plot.addItem(rect)
                self.rects.append(rect)

            self.level_html_format = (
                '<div style="text-align: center">'
                '<span style="color: #FFFFFF;font-size:12pt;">'
                "{}</span></div>"
            )

            self.level_text_item = pg.TextItem(
                fill=pg.mkColor(0, 150, 0),
                anchor=(0.5, 0),
            )

            no_detection_html = (
                '<div style="text-align: center">'
                '<span style="color: #FFFFFF;font-size:12pt;">'
                "{}</span></div>".format("No level detected")
            )

            self.no_detection_text_item = pg.TextItem(
                html=no_detection_html,
                fill=pg.mkColor("r"),
                anchor=(0.5, 0),
            )

            self.rect_plot.addItem(self.level_text_item)
            self.rect_plot.addItem(self.no_detection_text_item)
            self.level_text_item.setPos(self.num_rects / 2.0 + 1, self.num_rects + 2)
            self.level_text_item.hide()
            self.no_detection_text_item.setPos(self.num_rects / 2.0 + 1, self.num_rects + 2)
            self.no_detection_text_item.show()

        # Presence

        if self.ex_app_config.activate_presence:
            assert self.cargo_presence_config is not None
            assert estimated_frame_rate is not None

            self.history_length_n = int(round(PRESENCE_RUN_TIME_S * estimated_frame_rate) + 1)
            self.intra_history = np.zeros(self.history_length_n)
            self.inter_history = np.zeros(self.history_length_n)

            # Presence history plot

            self.presence_hist_plot = win.addPlot(
                row=0,
                col=1,
                title="Presence history",
            )
            self.presence_hist_plot.setMenuEnabled(False)
            self.presence_hist_plot.setMouseEnabled(x=False, y=False)
            self.presence_hist_plot.hideButtons()
            self.presence_hist_plot.showGrid(x=True, y=True)
            self.presence_hist_plot.setLabel("bottom", "Time (s)")
            self.presence_hist_plot.setLabel("left", "Score")
            self.presence_hist_plot.setXRange(-PRESENCE_RUN_TIME_S, 0)
            self.presence_history_smooth_max = et.utils.SmoothMax(estimated_frame_rate)
            self.presence_hist_plot.setYRange(0, 10)

            self.intra_dashed_pen = et.utils.pg_pen_cycler(1, width=2.5, style="--")
            self.intra_pen = et.utils.pg_pen_cycler(1)

            self.intra_hist_curve = self.presence_hist_plot.plot(pen=self.intra_pen)
            self.intra_limit_line = pg.InfiniteLine(angle=0, pen=self.intra_dashed_pen)
            self.presence_hist_plot.addItem(self.intra_limit_line)
            self.intra_limit_line.setPos(self.cargo_presence_config.intra_detection_threshold)
            self.intra_limit_line.setPen(self.intra_dashed_pen)

            self.inter_pen = et.utils.pg_pen_cycler(0)
            self.inter_dashed_pen = et.utils.pg_pen_cycler(0, width=2.5, style="--")

            self.inter_hist_curve = self.presence_hist_plot.plot(pen=self.inter_pen)
            self.inter_limit_line = pg.InfiniteLine(angle=0, pen=self.inter_dashed_pen)
            self.presence_hist_plot.addItem(self.inter_limit_line)
            self.inter_limit_line.setPos(self.cargo_presence_config.inter_detection_threshold)
            self.inter_limit_line.setPen(self.inter_dashed_pen)

            self.hist_xs = np.linspace(-PRESENCE_RUN_TIME_S, 0, self.history_length_n)

            # Presence detection plot

            self.presence_detection_plot = win.addPlot(row=1, col=1, title="Presence")
            self.presence_detection_plot.setAspectLocked()
            self.presence_detection_plot.hideAxis("left")
            self.presence_detection_plot.hideAxis("bottom")

            present_html_format = (
                '<div style="text-align: center">'
                '<span style="color: #FFFFFF;font-size:12pt;">'
                "{}</span></div>".format("Presence detected")
            )
            not_present_html = (
                '<div style="text-align: center">'
                '<span style="color: #FFFFFF;font-size:12pt;">'
                "{}</span></div>".format("No presence detected")
            )
            self.present_text_item = pg.TextItem(
                html=present_html_format,
                fill=pg.mkColor(0, 150, 0),
                anchor=(0.65, 0),
            )
            self.not_present_text_item = pg.TextItem(
                html=not_present_html,
                fill=pg.mkColor("r"),
                anchor=(0.6, 0),
            )

            self.presence_detection_plot.addItem(self.present_text_item)
            self.presence_detection_plot.addItem(self.not_present_text_item)
            self.present_text_item.setPos(self.num_rects / 2.0 + 1, self.num_rects + 2)
            self.not_present_text_item.setPos(self.num_rects / 2.0 + 1, self.num_rects + 2)
            self.present_text_item.hide()

            pen = pg.mkPen(None)
            rect_height = self.num_rects / 2.0
            rect_length = self.num_rects

            self.presence_rect = pg.QtWidgets.QGraphicsRectItem(
                0, rect_height, rect_length, rect_height
            )
            self.presence_rect.setPen(pen)
            self.presence_rect.setBrush(et.utils.pg_brush_cycler(7))
            self.presence_detection_plot.addItem(self.presence_rect)

    def draw_plot_job(self, *, result: ExAppResult) -> None:
        if result.mode == _Mode.DISTANCE:
            assert self.utilization_level_config is not None

            if self.ex_app_config.activate_presence:
                self.intra_history = np.zeros(self.history_length_n)
                self.inter_history = np.zeros(self.history_length_n)

            # Sweep plot

            distance = result.distance
            max_val_in_plot = 0
            if result.distance_processor_result is not None:
                for idx, processor_result in enumerate(result.distance_processor_result):
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

            if distance is not None:
                text_y_pos = self.sweep_plot.getAxis("left").range[1] * 0.95
                text_x_pos = (
                    self.sweep_plot.getAxis("bottom").range[1]
                    + self.sweep_plot.getAxis("bottom").range[0]
                ) / 2.0
                self.sweep_text_item.setPos(text_x_pos, text_y_pos)
                self.sweep_text_item.setHtml("Main peak distance: {:.3f} m".format(distance))
                self.sweep_text_item.show()

                self.sweep_main_peak_line.setPos(distance)
                self.sweep_main_peak_line.show()
            else:
                self.sweep_text_item.hide()
                self.sweep_main_peak_line.hide()

            # Utilization level plot

            # Show the percentage level plot if the plot width is greater than 400 pixels,
            # otherwise display the level as text.
            if self.plot_layout.width() < 400:
                if result.level_percent is None:
                    self.level_text_item.hide()
                    self.no_detection_text_item.show()
                elif result.level_percent > 0:
                    assert result.level_m is not None
                    assert result.level_percent is not None
                    level_text = "Utilization level: {:.1f} m, {:.0f} %".format(
                        result.level_m,
                        result.level_percent,
                    )
                    level_html = self.level_html_format.format(level_text)
                    self.level_text_item.setHtml(level_html)
                    self.level_text_item.show()
                    self.no_detection_text_item.hide()
                else:  # No detection
                    self.level_text_item.hide()
                    self.no_detection_text_item.show()

                for rect in self.rects:
                    rect.setVisible(False)
            else:
                if result.level_percent is None:  # No detection
                    for rect in self.rects:
                        rect.setBrush(et.utils.pg_brush_cycler(7))
                    self.level_text_item.hide()
                    self.no_detection_text_item.show()
                else:
                    self.bar_loc = int(
                        np.around(self.num_rects - result.level_percent / 100 * self.num_rects)
                    )
                    for rect in self.rects[self.bar_loc :]:
                        rect.setBrush(et.utils.pg_brush_cycler(0))

                    for rect in self.rects[: self.bar_loc]:
                        rect.setBrush(et.utils.pg_brush_cycler(7))

                    assert result.level_m is not None
                    assert result.level_percent is not None
                    level_text = "Utilization level: {:.2f} m, {:.0f} %".format(
                        result.level_m,
                        result.level_percent,
                    )
                    level_html = self.level_html_format.format(level_text)
                    self.level_text_item.setHtml(level_html)
                    self.level_text_item.show()
                    self.no_detection_text_item.hide()

                for rect in self.rects:
                    rect.setVisible(True)

        else:
            assert self.cargo_presence_config is not None

            # Presence history

            self.intra_history = np.roll(self.intra_history, -1)
            self.intra_history[-1] = result.intra_presence_score
            self.intra_hist_curve.setData(self.hist_xs, self.intra_history)

            self.inter_history = np.roll(self.inter_history, -1)
            self.inter_history[-1] = result.inter_presence_score
            self.inter_hist_curve.setData(self.hist_xs, self.inter_history)

            # Set y-range

            if np.isnan(self.intra_history).all():
                intra_m_hist = self.cargo_presence_config.intra_detection_threshold
            else:
                intra_m_hist = max(
                    float(np.nanmax(self.intra_history)),
                    self.cargo_presence_config.intra_detection_threshold * 1.05,
                )

            if np.isnan(self.inter_history).all():
                inter_m_hist = self.cargo_presence_config.inter_detection_threshold
            else:
                inter_m_hist = max(
                    float(np.nanmax(self.inter_history)),
                    self.cargo_presence_config.inter_detection_threshold * 1.05,
                )

            m_hist = max(intra_m_hist, inter_m_hist)
            m_hist = self.presence_history_smooth_max.update(m_hist)
            self.presence_hist_plot.setYRange(0, m_hist)

            # Presence detection plot

            if result.presence_detected:
                self.present_text_item.show()
                self.not_present_text_item.hide()
                self.presence_rect.setBrush(pg.mkColor(0, 150, 0))
            else:
                self.present_text_item.hide()
                self.not_present_text_item.show()
                self.presence_rect.setBrush(et.utils.pg_brush_cycler(7))


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
            title="Ex App parameters",
            factory_mapping={
                "container_size": pidgets.EnumPidgetFactory(
                    name_label_text="Container size:",
                    name_label_tooltip=get_attribute_docstring(ExAppConfig, "container_size"),
                    enum_type=ContainerSize,
                    label_mapping={
                        ContainerSize.CONTAINER_10_FT: "10 feet (3 m)",
                        ContainerSize.CONTAINER_20_FT: "20 feet (6 m)",
                        ContainerSize.CONTAINER_40_FT: "40 feet (12 m)",
                    },
                ),
                "activate_presence": pidgets.CheckboxPidgetFactory(
                    name_label_text="Activate presence detection",
                    name_label_tooltip=get_attribute_docstring(ExAppConfig, "presence"),
                ),
                "activate_utilization_level": pidgets.CheckboxPidgetFactory(
                    name_label_text="Activate utilization level",
                    name_label_tooltip=get_attribute_docstring(
                        ExAppConfig, "activate_utilization_level"
                    ),
                ),
            },
            config_type=ExAppConfig,
            parent=self.scrolly_widget,
        )
        self.config_editor.sig_update.connect(self._on_config_update)
        scrolly_layout.addWidget(self.config_editor)

        self.subsweep_status_utilization_level = SensorConfigEditor()
        self.subsweep_status_utilization_level.set_read_only(True)
        utiilization_level_status_widget = CollapsibleWidget(
            "Utilization level subsweep settings",
            self.subsweep_status_utilization_level.subsweep_group_box,
            self.scrolly_widget,
        )

        scrolly_layout.addWidget(utiilization_level_status_widget)

        self.utilization_level_config_editor = AttrsConfigEditor(
            title="Utilization level config parameters",
            factory_mapping=self._get_utilization_level_pidget_mapping(),
            config_type=UtilizationLevelConfig,
            parent=self.scrolly_widget,
        )
        self.utilization_level_config_editor.sig_update.connect(
            self._on_utilization_level_config_update
        )
        scrolly_layout.addWidget(self.utilization_level_config_editor)

        self.subsweep_status_cargo_presence = SensorConfigEditor()
        self.subsweep_status_cargo_presence.set_read_only(True)
        cargo_presence_status_widget = CollapsibleWidget(
            "Cargo presence subsweep settings",
            self.subsweep_status_cargo_presence.subsweep_group_box,
            self.scrolly_widget,
        )

        scrolly_layout.addWidget(cargo_presence_status_widget)
        self.cargo_presence_config_editor = AttrsConfigEditor(
            title="Cargo presence config parameters",
            factory_mapping=self._get_cargo_presence_pidget_mapping(),
            config_type=CargoPresenceConfig,
            parent=self.scrolly_widget,
        )
        self.cargo_presence_config_editor.sig_update.connect(self._on_cargo_presence_config_update)
        scrolly_layout.addWidget(self.cargo_presence_config_editor)

        self.sticky_widget.setLayout(sticky_layout)
        self.scrolly_widget.setLayout(scrolly_layout)

    @classmethod
    def _get_utilization_level_pidget_mapping(cls) -> PidgetFactoryMapping:
        return {
            "update_rate": pidgets.FloatPidgetFactory(
                name_label_text="Update rate:",
                name_label_tooltip=get_attribute_docstring(UtilizationLevelConfig, "update_rate"),
                suffix=" Hz",
                decimals=2,
                limits=(0.1, None),
            ),
            "signal_quality": pidgets.FloatSliderPidgetFactory(
                name_label_text="Signal quality:",
                name_label_tooltip=get_attribute_docstring(
                    UtilizationLevelConfig, "signal_quality"
                ),
                decimals=1,
                limits=(-10, 35),
                show_limit_values=False,
                limit_texts=("Less power", "Higher quality"),
            ),
            "threshold_sensitivity": pidgets.FloatSliderPidgetFactory(
                name_label_text="Threshold sensitivity:",
                name_label_tooltip=get_attribute_docstring(
                    UtilizationLevelConfig, "threshold_sensitivity"
                ),
                decimals=2,
                limits=(0, 1),
                show_limit_values=False,
            ),
        }

    @classmethod
    def _get_cargo_presence_pidget_mapping(cls) -> PidgetFactoryMapping:
        return {
            "burst_rate": pidgets.FloatPidgetFactory(
                name_label_text="Burst rate:",
                name_label_tooltip=get_attribute_docstring(CargoPresenceConfig, "burst_rate"),
                suffix=" Hz",
                decimals=2,
                limits=(0.01, 0.2),
            ),
            "update_rate": pidgets.FloatPidgetFactory(
                name_label_text="Update rate:",
                name_label_tooltip=get_attribute_docstring(CargoPresenceConfig, "update_rate"),
                suffix=" Hz",
                decimals=1,
                limits=(1, 100),
            ),
            "signal_quality": pidgets.FloatSliderPidgetFactory(
                name_label_text="Signal quality:",
                name_label_tooltip=get_attribute_docstring(CargoPresenceConfig, "signal_quality"),
                decimals=1,
                limits=(-10.0, 60.0),
            ),
            "sweeps_per_frame": pidgets.IntPidgetFactory(
                name_label_text="Sweeps per frame:",
                name_label_tooltip=get_attribute_docstring(
                    CargoPresenceConfig, "sweeps_per_frame"
                ),
                limits=(1, 4095),
            ),
            "inter_detection_threshold": pidgets.FloatSliderPidgetFactory(
                name_label_text="Inter detection threshold:",
                name_label_tooltip=get_attribute_docstring(
                    CargoPresenceConfig, "inter_detection_threshold"
                ),
                decimals=2,
                limits=(1, 20),
                log_scale=True,
            ),
            "intra_detection_threshold": pidgets.FloatSliderPidgetFactory(
                name_label_text="Intra detection threshold:",
                name_label_tooltip=get_attribute_docstring(
                    CargoPresenceConfig, "intra_detection_threshold"
                ),
                decimals=2,
                limits=(1, 20),
                log_scale=True,
            ),
        }

    def on_backend_state_update(self, state: Optional[SharedState]) -> None:
        if state is None:
            self.config_editor.set_data(None)
            self.utilization_level_config_editor.set_data(None)
            self.cargo_presence_config_editor.set_data(None)
            self.subsweep_status_utilization_level.set_data(None)
            self.subsweep_status_cargo_presence.set_data(None)
        else:
            self.sensor_id_pidget.set_data(state.sensor_id)
            self.config_editor.set_data(state.config)

            if state.config.utilization_level_config is not None:
                self.utilization_level_config_editor.set_data(
                    state.config.utilization_level_config
                )
                self.utilization_level_config_editor.setHidden(
                    not state.config.activate_utilization_level
                )
                start_m, end_m = state.config.container_size.distance_range
                distance_session_config = detector_config_to_session_config(
                    ExApp.get_distance_config(
                        state.config.utilization_level_config, start_m, end_m
                    ),
                    [state.sensor_id],
                )
                groups = distance_session_config.groups
                sensor_config = groups[0][state.sensor_id]
                self.subsweep_status_utilization_level.set_data(sensor_config)

            if state.config.cargo_presence_config is not None:
                self.cargo_presence_config_editor.set_data(state.config.cargo_presence_config)
                self.cargo_presence_config_editor.setHidden(not state.config.activate_presence)

                start_m, end_m = state.config.container_size.presence_range
                self.subsweep_status_cargo_presence.set_data(
                    PresenceDetector._get_sensor_config(
                        ExApp.get_presence_config(
                            state.config.cargo_presence_config, start_m, end_m
                        )
                    )
                )

            results = state.config._collect_validation_results()

            not_handled = self.config_editor.handle_validation_results(results)

            not_handled = self.cargo_presence_config_editor.handle_validation_results(not_handled)

            not_handled = self.utilization_level_config_editor.handle_validation_results(
                not_handled
            )

            not_handled = self.misc_error_view.handle_validation_results(not_handled)

            assert not_handled == []

    def on_app_model_update(self, app_model: AppModel) -> None:
        self.sensor_id_pidget.set_selectable_sensors(app_model.connected_sensors)

        visual_policies.apply_enabled_policy(
            visual_policies.config_editor_enabled,
            app_model,
            widgets=[
                self.config_editor,
                self.utilization_level_config_editor,
                self.cargo_presence_config_editor,
                self.sensor_id_pidget,
            ],
        )

        self.start_button.setEnabled(
            visual_policies.start_button_enabled(
                app_model, extra_condition=self.config_editor.is_ready
            )
        )
        self.stop_button.setEnabled(visual_policies.stop_button_enabled(app_model))

    def _on_config_update(self, config: ExAppConfig) -> None:
        BackendPlugin.update_config.rpc(self.app_model.put_task, config=config)

    def _on_utilization_level_config_update(self, config: UtilizationLevelConfig) -> None:
        BackendPlugin.update_utilization_level_config.rpc(self.app_model.put_task, config=config)

    def _on_cargo_presence_config_update(self, config: CargoPresenceConfig) -> None:
        BackendPlugin.update_cargo_presence_config.rpc(self.app_model.put_task, config=config)

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


CARGO_PLUGIN = PluginSpec(
    generation=PluginGeneration.A121,
    key="cargo",
    title="Cargo",
    docs_link="https://docs.acconeer.com/en/latest/example_apps/a121/cargo.html",
    description="Detects utilization level and presence in container.",
    family=PluginFamily.EXAMPLE_APP,
    presets=[
        PluginPresetBase(
            name="10 feet (3 m)",
            description="Container 10 feet (3 m)",
            preset_id=PluginPresetId.CONTAINER_10_FT,
        ),
        PluginPresetBase(
            name="20 feet (6 m)",
            description="Container 20 feet (6 m)",
            preset_id=PluginPresetId.CONTAINER_20_FT,
        ),
        PluginPresetBase(
            name="40 feet (12 m)",
            description="Container 40 feet (12 m)",
            preset_id=PluginPresetId.CONTAINER_40_FT,
        ),
        PluginPresetBase(
            name="No lens",
            description="No lens configuration",
            preset_id=PluginPresetId.NO_LENS,
        ),
    ],
    default_preset_id=PluginPresetId.NO_LENS,
)
