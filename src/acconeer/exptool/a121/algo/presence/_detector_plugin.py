# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Any, Callable, Optional

import attrs
import numpy as np
import qtawesome as qta

from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121.algo._plugins import (
    DetectorBackendPluginBase,
    DetectorPlotPluginBase,
    DetectorViewPluginBase,
)
from acconeer.exptool.app.new import (
    BUTTON_ICON_COLOR,
    AppModel,
    ConnectionState,
    GeneralMessage,
    HandledException,
    Message,
    Plugin,
    PluginFamily,
    PluginGeneration,
    PluginState,
    PluginStateMessage,
    get_temp_h5_path,
    is_task,
)
from acconeer.exptool.app.new.ui.plugin import (
    AttrsConfigEditor,
    GridGroupBox,
    PidgetFactoryMapping,
    pidgets,
    utils,
)

from ._detector import Detector, DetectorConfig, DetectorResult, _load_algo_data


log = logging.getLogger(__name__)


@attrs.mutable(kw_only=True)
class SharedState:
    sensor_id: int = attrs.field(default=1)
    config: DetectorConfig = attrs.field(factory=DetectorConfig)
    replaying: bool = attrs.field(default=False)


@attrs.frozen(kw_only=True)
class Save:
    config: DetectorConfig = attrs.field()


class BackendPlugin(DetectorBackendPluginBase[SharedState]):
    def __init__(self, callback: Callable[[Message], None], key: str) -> None:
        super().__init__(callback=callback, key=key)

        self._started: bool = False
        self._live_client: Optional[a121.Client] = None
        self._replaying_client: Optional[a121._ReplayingClient] = None
        self._recorder: Optional[a121.H5Recorder] = None
        self._opened_record: Optional[a121.H5Record] = None
        self._detector_instance: Optional[Detector] = None

        self.restore_defaults()

    @is_task
    def deserialize(self, *, data: bytes) -> None:
        try:
            obj = pickle.loads(data)
        except Exception:
            log.warning("Could not load pickled - pickle.loads() failed")
            return

        if not isinstance(obj, Save):
            log.warning("Could not load pickled - not the correct type")
            return

        if not isinstance(obj.config, DetectorConfig):
            log.warning("Could not load pickled - not the correct type")
            return

        self.shared_state.config = obj.config
        self.broadcast(sync=True)

    def _serialize(self) -> bytes:
        obj = Save(config=self.shared_state.config)
        return pickle.dumps(obj, protocol=4)

    def broadcast(self, sync: bool = False) -> None:
        super().broadcast()

        if sync:
            self.callback(GeneralMessage(name="sync", recipient="view_plugin"))

    @is_task
    def restore_defaults(self) -> None:
        self.shared_state = SharedState()
        self.broadcast(sync=True)

    @is_task
    def update_sensor_id(self, *, sensor_id: int) -> None:
        self.shared_state.sensor_id = sensor_id
        self.broadcast(sync=True)

    @property
    def _client(self) -> Optional[a121.Client]:
        if self._replaying_client is not None:
            return self._replaying_client

        return self._live_client

    def idle(self) -> bool:
        if self._started:
            self._get_next()
            return True
        else:
            return False

    def attach_client(self, *, client: Any) -> None:
        self._live_client = client

    def detach_client(self) -> None:
        self._live_client = None

    @is_task
    def update_config(self, *, config: DetectorConfig) -> None:
        self.shared_state.config = config
        self.broadcast()

    def teardown(self) -> None:
        self.callback(
            GeneralMessage(
                name="serialized",
                kwargs={
                    "generation": PluginGeneration.A121,
                    "key": self.key,
                    "data": self._serialize(),
                },
            )
        )
        self.detach_client()

    @is_task
    def load_from_file(self, *, path: Path) -> None:
        try:
            self._load_from_file_setup(path=path)
        except Exception as exc:
            self._opened_record = None
            self._replaying_client = None
            self.shared_state.replaying = False

            self.callback(PluginStateMessage(state=PluginState.LOADED_IDLE))
            raise HandledException("Could not load from file") from exc

        self.start_session(with_recorder=False)

        self.shared_state.replaying = True

        self.send_status_message(f"<b>Replaying from {path.name}</b>")
        self.broadcast(sync=True)

    def _load_from_file_setup(self, *, path: Path) -> None:
        r = a121.open_record(path)
        assert isinstance(r, a121.H5Record)
        self._opened_record = r
        self._replaying_client = a121._ReplayingClient(self._opened_record)

        algo_group = self._opened_record.get_algo_group(self.key)
        _, config = _load_algo_data(algo_group)
        self.shared_state.config = config

    @is_task
    def start_session(self, *, with_recorder: bool = True) -> None:
        if self._started:
            raise RuntimeError

        if self._client is None:
            raise RuntimeError

        if not self._client.connected:
            raise RuntimeError

        self._detector_instance = Detector(
            client=self._client,
            sensor_id=self.shared_state.sensor_id,
            detector_config=self.shared_state.config,
        )

        if with_recorder:
            self._recorder = a121.H5Recorder(get_temp_h5_path())
        else:
            self._recorder = None

        try:
            self._detector_instance.start(self._recorder)
        except Exception as exc:
            self.callback(PluginStateMessage(state=PluginState.LOADED_IDLE))
            raise HandledException("Could not start") from exc

        self._started = True

        self.broadcast()

        self.callback(
            GeneralMessage(
                name="setup",
                kwargs=dict(
                    detector_config=self.shared_state.config,
                    sensor_config=Detector._get_sensor_config(self.shared_state.config),
                ),
                recipient="plot_plugin",
            )
        )
        self.callback(PluginStateMessage(state=PluginState.LOADED_BUSY))

    @is_task
    def stop_session(self) -> None:
        if not self._started:
            raise RuntimeError

        if self._detector_instance is None:
            raise RuntimeError

        try:
            self._detector_instance.stop()
        except Exception as exc:
            raise HandledException("Failure when stopping session") from exc
        finally:
            if self._recorder is not None:
                assert self._recorder.path is not None
                path = Path(self._recorder.path)
                self.callback(GeneralMessage(name="saveable_file", data=path))
                self._recorder = None

            if self.shared_state.replaying:
                assert self._opened_record is not None
                self._opened_record.close()

                self._opened_record = None
                self._replaying_client = None

                self.shared_state.replaying = False

            self._started = False
            self.broadcast()
            self.callback(PluginStateMessage(state=PluginState.LOADED_IDLE))
            self.callback(GeneralMessage(name="result_tick_time", data=None))

    def _get_next(self) -> None:
        if not self._started:
            raise RuntimeError

        if self._detector_instance is None:
            raise RuntimeError

        try:
            result = self._detector_instance.get_next()
        except a121._StopReplay:
            self.stop_session()
            return
        except Exception as exc:
            try:
                self.stop_session()
            except Exception:
                pass

            raise HandledException("Failed to get_next") from exc

        self.callback(
            GeneralMessage(name="result_tick_time", data=result.service_result.tick_time)
        )

        self.callback(GeneralMessage(name="plot", data=result, recipient="plot_plugin"))


class PlotPlugin(DetectorPlotPluginBase):
    def __init__(self, *, plot_layout: pg.GraphicsLayout, app_model: AppModel) -> None:
        super().__init__(plot_layout=plot_layout, app_model=app_model)

    def setup_from_message(self, message: GeneralMessage) -> None:
        assert message.kwargs is not None
        self.setup(**message.kwargs)

    def update_from_message(self, message: GeneralMessage) -> None:
        assert isinstance(message.data, DetectorResult)
        self.update(message.data)

    def setup(self, detector_config: DetectorConfig, sensor_config: a121.SensorConfig) -> None:
        self.detector_config = detector_config
        self.distances = np.linspace(
            detector_config.start_m, detector_config.end_m, sensor_config.num_points
        )

        self.history_length_s = 10

        max_num_of_sectors = max(6, self.distances.size // 3)
        self.sector_size = max(1, -(-self.distances.size // max_num_of_sectors))
        self.num_sectors = -(-self.distances.size // self.sector_size)
        self.sector_offset = (self.num_sectors * self.sector_size - self.distances.size) // 2

        win = self.plot_layout

        self.limit_lines = []
        dashed_pen = pg.mkPen("k", width=2.5)  # , style=QtCore.Qt.DashLine

        # Amplitude plot

        self.ampl_plot = win.addPlot(
            row=0,
            col=0,
            title="Amplitude, sweeps (orange), mean sweep (blue)",
        )

        self.ampl_plot.setMenuEnabled(False)
        self.ampl_plot.setMouseEnabled(x=False, y=False)
        self.ampl_plot.hideButtons()
        self.ampl_plot.showGrid(x=True, y=True)
        self.ampl_plot.setLabel("bottom", "Distance (m)")
        self.ampl_plot.setLabel("left", "Amplitude")

        self.ampl_plot.setYRange(0, 2**16)

        self.frame_scatter = pg.ScatterPlotItem(
            size=10,
            brush=et.utils.pg_brush_cycler(1),
        )
        self.mean_sweep_scatter = pg.ScatterPlotItem(
            size=10,
            brush=et.utils.pg_brush_cycler(0),
        )

        self.ampl_plot.addItem(self.frame_scatter)
        self.ampl_plot.addItem(self.mean_sweep_scatter)
        self.frame_smooth_limits = et.utils.SmoothLimits(self.detector_config.frame_rate)

        # Noise estimation plot

        self.noise_plot = win.addPlot(
            row=1,
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

        self.move_plot = win.addPlot(
            row=2,
            col=0,
            title="Depthwise presence",
        )
        self.move_plot.setMenuEnabled(False)
        self.move_plot.setMouseEnabled(x=False, y=False)
        self.move_plot.hideButtons()
        self.move_plot.showGrid(x=True, y=True)
        self.move_plot.setLabel("bottom", "Distance (m)")
        self.move_plot.setLabel("left", "Norm. ampl.")
        zero_curve = self.move_plot.plot(self.distances, np.zeros_like(self.distances))
        self.inter_curve = self.move_plot.plot()
        self.total_curve = self.move_plot.plot()
        self.move_smooth_max = et.utils.SmoothMax(
            self.detector_config.frame_rate,
            tau_decay=1.0,
            tau_grow=0.25,
        )

        self.move_depth_line = pg.InfiniteLine(pen=pg.mkPen("k", width=1.5))
        self.move_depth_line.hide()
        self.move_plot.addItem(self.move_depth_line)
        limit_line = pg.InfiniteLine(angle=0, pen=dashed_pen)
        self.move_plot.addItem(limit_line)
        self.limit_lines.append(limit_line)

        fbi = pg.FillBetweenItem(
            zero_curve,
            self.inter_curve,
            brush=et.utils.pg_brush_cycler(0),
        )
        self.move_plot.addItem(fbi)

        fbi = pg.FillBetweenItem(
            self.inter_curve,
            self.total_curve,
            brush=et.utils.pg_brush_cycler(1),
        )
        self.move_plot.addItem(fbi)

        # Presence history plot

        self.move_hist_plot = pg.PlotItem(title="Presence history")
        self.move_hist_plot.setMenuEnabled(False)
        self.move_hist_plot.setMouseEnabled(x=False, y=False)
        self.move_hist_plot.hideButtons()
        self.move_hist_plot.showGrid(x=True, y=True)
        self.move_hist_plot.setLabel("bottom", "Time (s)")
        self.move_hist_plot.setLabel("left", "Score")
        self.move_hist_plot.setXRange(-self.history_length_s, 0)
        self.history_smooth_max = et.utils.SmoothMax(self.detector_config.frame_rate)
        self.move_hist_plot.setYRange(0, 10)

        self.move_hist_curve = self.move_hist_plot.plot(pen=et.utils.pg_pen_cycler())
        limit_line = pg.InfiniteLine(angle=0, pen=dashed_pen)
        self.move_hist_plot.addItem(limit_line)
        self.limit_lines.append(limit_line)

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

        self.move_hist_plot.addItem(self.present_text_item)
        self.move_hist_plot.addItem(self.not_present_text_item)
        self.present_text_item.hide()
        self.not_present_text_item.hide()

        for line in self.limit_lines:
            line.setPos(self.detector_config.detection_threshold)

        # Sector plot

        self.sector_plot = pg.PlotItem()
        self.sector_plot.setAspectLocked()
        self.sector_plot.hideAxis("left")
        self.sector_plot.hideAxis("bottom")
        self.sectors = []

        pen = pg.mkPen("k", width=1)
        span_deg = 25
        for r in np.flip(np.arange(self.num_sectors) + 1):
            sector = pg.QtGui.QGraphicsEllipseItem(-r, -r, r * 2, r * 2)
            sector.setStartAngle(-16 * span_deg)
            sector.setSpanAngle(16 * span_deg * 2)
            sector.setPen(pen)
            self.sector_plot.addItem(sector)
            self.sectors.append(sector)

        self.sectors.reverse()

        sublayout = win.addLayout(row=3, col=0)
        sublayout.layout.setColumnStretchFactor(0, 2)
        sublayout.addItem(self.move_hist_plot, col=0)
        sublayout.addItem(self.sector_plot, col=1)

    def update(self, data: DetectorResult) -> None:
        amplitudes = np.abs(data.processor_extra_result.frame)
        self.frame_scatter.setData(
            np.tile(self.distances, self.detector_config.sweeps_per_frame),
            amplitudes.flatten(),
        )

        self.mean_sweep_scatter.setData(self.distances, data.processor_extra_result.mean_sweep)
        self.ampl_plot.setYRange(*self.frame_smooth_limits.update(amplitudes))

        noise = data.processor_extra_result.lp_noise
        self.noise_curve.setData(self.distances, noise)
        self.noise_plot.setYRange(0, self.noise_smooth_max.update(noise))

        movement_x = data.presence_distance

        move_ys = data.processor_extra_result.depthwise_presence
        self.inter_curve.setData(self.distances, data.processor_extra_result.inter)
        self.total_curve.setData(self.distances, move_ys)
        m = self.move_smooth_max.update(np.max(move_ys))
        m = max(m, 2 * self.detector_config.detection_threshold)
        self.move_plot.setYRange(0, m)
        self.move_depth_line.setPos(movement_x)
        self.move_depth_line.setVisible(bool(data.presence_detected))

        move_hist_ys = data.processor_extra_result.presence_history
        move_hist_xs = np.linspace(-self.history_length_s, 0, len(move_hist_ys))

        m_hist = max(float(np.max(move_hist_ys)), self.detector_config.detection_threshold * 1.05)
        m_hist = self.history_smooth_max.update(m_hist)

        self.move_hist_plot.setYRange(0, m_hist)
        self.move_hist_curve.setData(move_hist_xs, move_hist_ys)
        self.set_present_text_y_pos(m_hist)

        if data.presence_detected:
            present_text = "Presence detected at {:.0f} cm".format(movement_x * 100)
            present_html = self.present_html_format.format(present_text)
            self.present_text_item.setHtml(present_html)

            self.present_text_item.show()
            self.not_present_text_item.hide()
        else:
            self.present_text_item.hide()
            self.not_present_text_item.show()

        brush = et.utils.pg_brush_cycler(0)
        for sector in self.sectors:
            sector.setBrush(brush)

        if data.presence_detected:
            index = (
                data.processor_extra_result.presence_distance_index + self.sector_offset
            ) // self.sector_size
            self.sectors[index].setBrush(et.utils.pg_brush_cycler(1))

    def set_present_text_y_pos(self, y):
        self.present_text_item.setPos(-self.history_length_s / 2, 0.95 * y)
        self.not_present_text_item.setPos(-self.history_length_s / 2, 0.95 * y)


class ViewPlugin(DetectorViewPluginBase):
    def __init__(self, app_model: AppModel, view_widget: QWidget) -> None:
        super().__init__(app_model=app_model, view_widget=view_widget)

        self.view_layout = QVBoxLayout(self.view_widget)
        self.view_layout.setContentsMargins(0, 0, 0, 0)
        self.view_widget.setLayout(self.view_layout)

        # TODO: Fix parents

        self.start_button = QPushButton(
            qta.icon("fa5s.play-circle", color=BUTTON_ICON_COLOR),
            "Start measurement",
            self.view_widget,
        )
        self.start_button.setShortcut("space")
        self.start_button.clicked.connect(self._send_start_request)
        self.stop_button = QPushButton(
            qta.icon("fa5s.stop-circle", color=BUTTON_ICON_COLOR),
            "Stop",
            self.view_widget,
        )
        self.stop_button.setShortcut("space")
        self.stop_button.clicked.connect(self._send_stop_request)

        self.defaults_button = QPushButton(
            qta.icon("mdi6.restore", color=BUTTON_ICON_COLOR),
            "Reset settings and calibrations",
            self.view_widget,
        )
        self.defaults_button.clicked.connect(self._send_defaults_request)

        button_group = GridGroupBox("Controls", parent=self.view_widget)
        button_group.layout().addWidget(self.start_button, 0, 0)
        button_group.layout().addWidget(self.stop_button, 0, 1)
        button_group.layout().addWidget(self.defaults_button, 1, 0, 1, -1)
        self.view_layout.addWidget(button_group)

        sensor_selection_group = utils.VerticalGroupBox(
            "Sensor selection", parent=self.view_widget
        )
        self.sensor_id_pidget = pidgets.SensorIdParameterWidgetFactory(items=[]).create(
            parent=sensor_selection_group
        )
        self.sensor_id_pidget.sig_parameter_changed.connect(self._on_sensor_id_update)
        sensor_selection_group.layout().addWidget(self.sensor_id_pidget)
        self.view_layout.addWidget(sensor_selection_group)

        self.config_editor = AttrsConfigEditor[DetectorConfig](
            title="Detector parameters",
            factory_mapping=self._get_pidget_mapping(),
            parent=self.view_widget,
        )
        self.config_editor.sig_update.connect(self._on_config_update)
        self.view_layout.addWidget(self.config_editor)

        self.view_layout.addStretch(1)

    @classmethod
    def _get_pidget_mapping(cls) -> PidgetFactoryMapping:
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
            "step_length": pidgets.OptionalIntParameterWidgetFactory(
                name_label_text="Step length",
                checkbox_label_text="Override",
                limits=(1, None),
                init_set_value=24,
            ),
            "detection_threshold": pidgets.FloatSliderParameterWidgetFactory(
                name_label_text="Detection threshold",
                decimals=2,
                limits=(0, 5),
            ),
            "frame_rate": pidgets.FloatParameterWidgetFactory(
                name_label_text="Frame rate",
                suffix=" Hz",
                decimals=1,
                limits=(1, 100),
            ),
            "sweeps_per_frame": pidgets.IntParameterWidgetFactory(
                name_label_text="Sweeps per frame",
                limits=(1, 4095),
            ),
            "hwaas": pidgets.IntParameterWidgetFactory(
                name_label_text="HWAAS",
                limits=(1, 511),
            ),
        }

    def on_app_model_update(self, app_model: AppModel) -> None:
        state = app_model.backend_plugin_state
        self.sensor_id_pidget.update_available_sensor_list(app_model._a121_server_info)

        if state is None:
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(False)
            self.defaults_button.setEnabled(False)

            self.config_editor.set_data(None)
            self.config_editor.setEnabled(False)
            self.sensor_id_pidget.set_parameter(None)

            return

        assert isinstance(state, SharedState)

        self.defaults_button.setEnabled(app_model.plugin_state == PluginState.LOADED_IDLE)

        self.config_editor.setEnabled(app_model.plugin_state == PluginState.LOADED_IDLE)
        self.config_editor.set_data(state.config)
        self.sensor_id_pidget.set_parameter(state.sensor_id)
        self.sensor_id_pidget.setEnabled(app_model.plugin_state.is_steady)

        ready_for_session = (
            app_model.plugin_state == PluginState.LOADED_IDLE
            and app_model.connection_state == ConnectionState.CONNECTED
        )

        self.start_button.setEnabled(ready_for_session)
        self.stop_button.setEnabled(app_model.plugin_state == PluginState.LOADED_BUSY)

    # TODO: move to detector base (?)
    def _on_config_update(self, config: DetectorConfig) -> None:
        self.app_model.put_backend_plugin_task("update_config", {"config": config})

    # TODO: move to detector base (?)
    def handle_message(self, message: GeneralMessage) -> None:
        if message.name == "sync":
            log.debug(f"{type(self).__name__} syncing")

            self.config_editor.sync()
        else:
            raise RuntimeError("Unknown message")

    # TODO: move to detector base (?)
    def _send_start_request(self) -> None:
        self.app_model.put_backend_plugin_task("start_session", on_error=self.app_model.emit_error)
        self.app_model.set_plugin_state(PluginState.LOADED_STARTING)

    # TODO: move to detector base (?)
    def _send_stop_request(self) -> None:
        self.app_model.put_backend_plugin_task("stop_session", on_error=self.app_model.emit_error)
        self.app_model.set_plugin_state(PluginState.LOADED_STOPPING)

    def _send_defaults_request(self) -> None:
        self.app_model.put_backend_plugin_task("restore_defaults")

    def _on_sensor_id_update(self, sensor_id: int) -> None:
        self.app_model.put_backend_plugin_task("update_sensor_id", {"sensor_id": sensor_id})

    # TODO: move to detector base (?)
    def teardown(self) -> None:
        self.view_layout.deleteLater()


PRESENCE_DETECTOR_PLUGIN = Plugin(
    generation=PluginGeneration.A121,
    key="presence_detector",
    title="Presence detector",
    # description="",
    family=PluginFamily.DETECTOR,
    backend_plugin=BackendPlugin,
    plot_plugin=PlotPlugin,
    view_plugin=ViewPlugin,
)
