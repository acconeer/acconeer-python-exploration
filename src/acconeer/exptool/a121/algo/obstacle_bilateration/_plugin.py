# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import logging
from enum import Enum, auto
from typing import Callable, Optional

import attrs
import h5py
import numpy as np

from PySide6.QtGui import QTransform
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121, opser
from acconeer.exptool.a121._h5_utils import _create_h5_string_dataset
from acconeer.exptool.a121.algo._plugins import (
    A121BackendPluginBase,
    A121ViewPluginBase,
)
from acconeer.exptool.a121.algo.obstacle import (
    BilateratorResult,
    DetailedStatus,
    Detector,
    DetectorConfig,
    DetectorContext,
    DetectorResult,
)
from acconeer.exptool.a121.algo.obstacle._detector import _load_algo_data
from acconeer.exptool.a121.algo.obstacle._detector_plugin import ViewPlugin as ObstacleViewPlugin
from acconeer.exptool.app.new import (
    AppModel,
    AttrsConfigEditor,
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
    TwoSensorIdsEditor,
    backend,
    icons,
    is_task,
    pidgets,
)

from ._configs import get_default_detector_config


log = logging.getLogger(__name__)


@attrs.mutable(kw_only=True)
class SharedState:
    sensor_ids: list[int] = attrs.field(factory=lambda: [2, 3])
    context: DetectorContext = attrs.field(factory=DetectorContext)
    config: DetectorConfig = attrs.field(factory=DetectorConfig)


class PluginPresetId(Enum):
    DEFAULT = auto()


@attrs.mutable(kw_only=True)
class BilaterationPreset:
    detector_config: DetectorConfig = attrs.field()


@attrs.frozen(kw_only=True)
class SetupMessage(GeneralMessage):
    bilateration_config: DetectorConfig
    sensor_ids: list[int] = attrs.field(factory=list)
    name: str = attrs.field(default="setup", init=False)
    recipient: backend.RecipientLiteral = attrs.field(default="plot_plugin", init=False)


class BackendPlugin(A121BackendPluginBase[SharedState]):
    def __init__(
        self, callback: Callable[[Message], None], generation: PluginGeneration, key: str
    ) -> None:
        super().__init__(callback=callback, generation=generation, key=key)

        self._detector_instance: Optional[Detector] = None

        self.restore_defaults()

    def _load_from_cache(self, file: h5py.File) -> None:
        self.shared_state.config = DetectorConfig.from_json(file["config"][()])
        self.shared_state.context = opser.deserialize(file["context"], DetectorContext)

    @is_task
    def restore_defaults(self) -> None:
        self.shared_state = SharedState(config=get_default_detector_config())
        self.broadcast()

    def _sync_sensor_ids(self) -> None:
        if self.client is not None:
            sensor_ids = self.client.server_info.connected_sensors

            for i in range(len(self.shared_state.sensor_ids)):
                if len(sensor_ids) > 0 and self.shared_state.sensor_ids[i] not in sensor_ids:
                    self.shared_state.sensor_ids[i] = sensor_ids[0]

            self.broadcast()

    @is_task
    def update_config(self, *, config: DetectorConfig) -> None:
        self.shared_state.config = config
        self.broadcast()

    @is_task
    def update_processor_config(self, *, config: DetectorConfig) -> None:
        self.shared_state.config = config
        self.broadcast()

    @is_task
    def set_preset(self, preset_id: int) -> None:
        if preset_id == PluginPresetId.DEFAULT.value:
            self.restore_defaults()
            self.broadcast()
        else:
            assert False  # <- bomb that will blow up if/when we add a second preset

    @is_task
    def update_sensor_ids(self, *, sensor_ids: list[int]) -> None:
        self.shared_state.sensor_ids = sensor_ids
        self.broadcast()

    def save_to_cache(self, file: h5py.File) -> None:
        _create_h5_string_dataset(file, "config", self.shared_state.config.to_json())
        opser.serialize(self.shared_state.context, file.create_group("context"))

    def load_from_record_setup(self, *, record: a121.H5Record) -> None:
        algo_group = record.get_algo_group(self.key)
        _, config, context = _load_algo_data(algo_group)
        self.shared_state.config = config
        self.shared_state.context = context

        sensor_ids: list[int] = []
        for entry in record.session_config.groups:
            sensor_ids.extend(entry.keys())
        self.shared_state.sensor_ids = sensor_ids

        self.broadcast()

    def _start_session(self, recorder: Optional[a121.H5Recorder]) -> None:
        assert self.client

        self._detector_instance = Detector(
            client=self.client,
            sensor_ids=self.shared_state.sensor_ids,
            detector_config=self.shared_state.config,
            context=self.shared_state.context,
        )
        if recorder is None:
            self._detector_instance.start()
        else:
            obstacle_bilateration_algo_group = recorder.require_algo_group("obstacle_bilateration")
            self._detector_instance.start(recorder, obstacle_bilateration_algo_group)

        self.callback(
            SetupMessage(
                bilateration_config=self.shared_state.config,
                sensor_ids=self.shared_state.sensor_ids,
            )
        )

    def end_session(self) -> None:
        if self._detector_instance is None:
            raise RuntimeError
        if self._recorder is not None:
            self._recorder.close()
        self._detector_instance.stop()

    def get_next(self) -> None:
        if self._detector_instance is None:
            raise RuntimeError
        detector_result = self._detector_instance.get_next()

        assert self.client is not None
        self.callback(backend.PlotMessage(result=detector_result))

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
            )
            self._detector_instance.calibrate_detector()
        except Exception as exc:
            raise HandledException("Failed to calibrate detector") from exc
        finally:
            self.callback(PluginStateMessage(state=PluginState.LOADED_IDLE))

        self.shared_state.context = self._detector_instance.context

        self.broadcast()


PLOT_HISTORY_FRAMES = 50


class PlotPlugin(PgPlotPlugin):
    def __init__(self, app_model: AppModel) -> None:
        super().__init__(app_model=app_model)
        self._plot_job = None
        self._is_setup = False

    def handle_message(self, message: backend.GeneralMessage) -> None:
        if isinstance(message, backend.PlotMessage):
            self._plot_job = message.result
        elif isinstance(message, SetupMessage):
            self.setup(
                message.bilateration_config,
                message.sensor_ids,
            )
            self._is_setup = True
        else:
            log.warn(f"{self.__class__.__name__} got an unsupported command: {message.name!r}.")

    def draw(self) -> None:
        if not self._is_setup or self._plot_job is None:
            return

        try:
            self.draw_plot_job(detector_result=self._plot_job)
        finally:
            self._plot_job = None

    def setup(
        self,
        detector_config: DetectorConfig,
        sensor_ids: list[int],
    ) -> None:
        self.plot_layout.clear()

        self.detector_config = detector_config
        self.sensor_ids = sensor_ids

        self.fftmap_plots: list[pg.PlotItem] = []
        self.fftmap_images: list[pg.ImageItem] = []
        self.range_hist_curves: list[pg.PlotDataItem] = []
        self.angle_hist_curves: list[pg.PlotDataItem] = []

        self.obst_vel_ys = 2 * [np.nan * np.ones(PLOT_HISTORY_FRAMES)]
        self.obst_dist_ys = 2 * [np.nan * np.ones(PLOT_HISTORY_FRAMES)]
        self.obst_bil_ys = np.nan * np.ones(PLOT_HISTORY_FRAMES)
        self.hist_x = np.linspace(-100, 0, PLOT_HISTORY_FRAMES)  # TODO: should no be hard coded

        win = self.plot_layout

        for i_s in range(2):
            p = win.addPlot(row=0, col=i_s, title=f"FFT Map, sensor {self.sensor_ids[i_s]} ")

            im = pg.ImageItem(autoDownsample=True)
            im.setLookupTable(et.utils.pg_mpl_cmap("viridis"))
            self.fftmap_images.append(im)

            p.setLabel("bottom", "Distance (cm)")
            p.setLabel("left", "Velocity (cm/s)")
            p.addItem(im)

            self.fftmap_plots.append(p)

            self.angle_hist = pg.PlotItem(title="Angle/velocity history")
            self.angle_hist.showGrid(x=True, y=True)
            self.angle_hist.setLabel("bottom", "Time (frames)")
            self.angle_hist.setLabel("left", "velocity (cm/s)")
            self.angle_hist.setXRange(-100, 0)
            self.angle_hist.addLegend()
            self.angle_hist_curves.append(self.angle_hist.plot(symbolSize=5, symbol="o"))

            sublayout = win.addLayout(
                row=1,
                col=i_s,
                colspan=1,
            )

            sublayout.layout.setColumnStretchFactor(0, 1)
            sublayout.addItem(self.angle_hist, row=0, col=0)

            self.range_hist = pg.PlotItem(title="Range history")
            self.range_hist.showGrid(x=True, y=True)
            self.range_hist.setLabel("bottom", "Time (frames)")
            self.range_hist.setLabel("left", "Range (cm)")
            self.range_hist.setXRange(-100, 0)
            self.range_hist.addLegend()
            self.range_hist_curves.append(self.range_hist.plot(symbolSize=5, symbol="o"))

            sublayout = win.addLayout(
                row=2,
                col=i_s,
                colspan=1,
            )

            sublayout.layout.setColumnStretchFactor(0, 1)
            sublayout.addItem(self.range_hist, row=0, col=0)

        self.bil_hist_plot = pg.PlotItem(title="Bilateration history")

        self.bil_hist_plot.showGrid(x=True, y=True)
        self.bil_hist_plot.setLabel("bottom", "Time (frames)")
        self.bil_hist_plot.setLabel("left", "Bilateration angle (deg)")
        self.bil_hist_plot.setXRange(-100, 0)
        self.bil_hist_plot.setYRange(-90, 90)
        self.bil_hist_plot.addLegend()

        self.bil_hist_curve = self.bil_hist_plot.plot(pen=et.utils.pg_pen_cycler(1))

        sublayout = win.addLayout(row=3, col=0, colspan=2)
        sublayout.layout.setColumnStretchFactor(0, 2)
        sublayout.addItem(self.bil_hist_plot, row=0, col=0)

        self.setup_is_done = True

    def draw_plot_job(self, *, detector_result: DetectorResult) -> None:
        # Plot sweep data from both distance detectors.

        for i_s in range(2):
            pr = detector_result.processor_results[self.sensor_ids[i_s]]

            fftmap = pr.subsweeps_extra_results[0].fft_map

            spf = fftmap.shape[0]
            r = 100 * pr.subsweeps_extra_results[0].r

            transform = QTransform()
            transform.translate(
                r[0], -100 * pr.extra_result.dv * spf / 2 - 0.5 * 100 * pr.extra_result.dv
            )
            transform.scale(r[1] - r[0], 100 * pr.extra_result.dv)

            self.fftmap_images[i_s].setTransform(transform)

            self.fftmap_images[i_s].updateImage(
                np.fft.fftshift(fftmap, 0).T,
                levels=(0, 1.05 * np.max(fftmap)),
            )

            v = pr.targets[0].velocity if pr.targets else np.nan

            self.obst_vel_ys[i_s] = np.roll(self.obst_vel_ys[i_s], -1)
            self.obst_vel_ys[i_s][-1] = 100 * v  # m/s -> cm/s

            if np.isnan(self.obst_vel_ys[i_s]).all():
                self.angle_hist_curves[i_s].setVisible(False)
            else:
                self.angle_hist_curves[i_s].setVisible(True)
                self.angle_hist_curves[i_s].setData(
                    self.hist_x, self.obst_vel_ys[i_s], connect="finite"
                )

            r_targets = pr.targets[0].distance if pr.targets else np.nan

            self.obst_dist_ys[i_s] = np.roll(self.obst_dist_ys[i_s], -1)
            self.obst_dist_ys[i_s][-1] = 100 * r_targets  # m -> cm

            if np.isnan(self.obst_dist_ys[i_s]).all():
                self.range_hist_curves[i_s].setVisible(False)
            else:
                self.range_hist_curves[i_s].setVisible(True)
                self.range_hist_curves[i_s].setData(
                    self.hist_x, self.obst_dist_ys[i_s], connect="finite"
                )

        assert isinstance(detector_result.bilateration_result, BilateratorResult)

        beta = (
            detector_result.bilateration_result.beta_degs[0]
            if detector_result.bilateration_result.beta_degs
            else np.nan
        )

        self.obst_bil_ys = np.roll(self.obst_bil_ys, -1)
        self.obst_bil_ys[-1] = beta

        if np.isnan(self.obst_bil_ys).all():
            self.bil_hist_curve.setVisible(False)
        else:
            self.bil_hist_curve.setVisible(True)
            self.bil_hist_curve.setData(self.hist_x, self.obst_bil_ys, connect="finite")


class ViewPlugin(A121ViewPluginBase):
    TEXT_MSG_MAP = {
        DetailedStatus.OK: "Ready to start.",
        DetailedStatus.END_LESSER_THAN_START: "'Range end' point must be greater than 'Range "
        + "start'.",
        DetailedStatus.SENSOR_IDS_NOT_UNIQUE: "Select two different sensor IDs.",
        DetailedStatus.CONTEXT_MISSING: "Run detector calibration.",
        DetailedStatus.CALIBRATION_MISSING: "Run detector calibration.",
        DetailedStatus.CONFIG_MISMATCH: (
            "Current configuration does not match the configuration "
            + "used during detector calibration. Run detector calibration."
        ),
    }

    def __init__(self, app_model: AppModel) -> None:
        super().__init__(app_model=app_model)

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

        self.misc_error_view = MiscErrorView(self.scrolly_widget)
        scrolly_layout.addWidget(self.misc_error_view)

        sensor_selection_group = GroupBox.grid("Sensor selection", parent=self.scrolly_widget)
        self.two_sensor_id_editor = TwoSensorIdsEditor(name_label_texts=["Left", "Right"])
        sensor_selection_group.layout().addWidget(self.two_sensor_id_editor, 0, 0)
        scrolly_layout.addWidget(sensor_selection_group)

        self.config_editor = AttrsConfigEditor(
            title="Obstacle detector parameters",
            config_type=DetectorConfig,
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
        return {}

    @classmethod
    def _get_pidget_mapping(cls) -> PidgetFactoryMapping:
        obstacle_dict = dict(ObstacleViewPlugin.get_pidget_mapping())
        bilateration_dict = {
            "bilateration_sensor_spacing_m": pidgets.FloatPidgetFactory(
                name_label_text="Sensor spacing:",
                suffix=" m",
                decimals=3,
            ),
        }
        obstacle_dict.update(bilateration_dict)
        return obstacle_dict

    def on_backend_state_update(self, state: Optional[SharedState]) -> None:
        if state is None:
            self.config_editor.set_data(None)
            self.message_box.setText("")
        else:
            self.config_editor.set_data(state.config)
            self.two_sensor_id_editor.set_data(state.sensor_ids)

            detector_status = Detector.get_detector_status(
                state.config, state.context, state.sensor_ids
            )

            self.message_box.setText(self.TEXT_MSG_MAP[detector_status.detector_state])

            validation_results = state.config._collect_validation_results()

            not_handled = self.config_editor.handle_validation_results(validation_results)
            not_handled = self.misc_error_view.handle_validation_results(not_handled)
            assert not_handled == []

    def on_app_model_update(self, app_model: AppModel) -> None:
        self.config_editor.setEnabled(app_model.plugin_state == PluginState.LOADED_IDLE)
        self.defaults_button.setEnabled(app_model.plugin_state == PluginState.LOADED_IDLE)
        self.two_sensor_id_editor.setEnabled(app_model.plugin_state == PluginState.LOADED_IDLE)

        self.stop_button.setEnabled(app_model.plugin_state == PluginState.LOADED_BUSY)

        self.two_sensor_id_editor.set_selectable_sensors(app_model.connected_sensors)

        state = app_model.backend_plugin_state

        if state is None:
            detector_ready = False
            ready_to_measure = False
        else:
            detector_status = Detector.get_detector_status(
                state.config, state.context, state.sensor_ids
            )
            detector_ready = detector_status.ready_to_start

            ready_to_measure = (
                app_model.is_ready_for_session()
                and self._config_valid(state)
                and self.config_editor.is_ready
                and detector_status.detector_state != DetailedStatus.SENSOR_IDS_NOT_UNIQUE
            )

        self.calibrate_detector_button.setEnabled(ready_to_measure)
        self.start_button.setEnabled(detector_ready and ready_to_measure)

    def _config_valid(self, state: SharedState) -> bool:
        try:
            state.config.validate()
        except a121.ValidationResult:
            return False
        else:
            return True

    def _on_config_update(self, config: DetectorConfig) -> None:
        BackendPlugin.update_config.rpc(self.app_model.put_task, config=config)

    def _on_processor_config_update(self, config: DetectorConfig) -> None:
        BackendPlugin.update_processor_config.rpc(self.app_model.put_task, config=config)

    def _on_sensor_ids_update(self, sensor_ids: list[int]) -> None:
        BackendPlugin.update_sensor_ids.rpc(self.app_model.put_task, sensor_ids=sensor_ids)

    def _on_calibrate_detector(self) -> None:
        BackendPlugin.calibrate_detector.rpc(self.app_model.put_task)

    def _send_defaults_request(self) -> None:
        BackendPlugin.restore_defaults.rpc(self.app_model.put_task)


class PluginSpec(PluginSpecBase):
    def create_backend_plugin(
        self, callback: Callable[[Message], None], key: str
    ) -> BackendPlugin:
        return BackendPlugin(callback, generation=self.generation, key=key)

    def create_view_plugin(self, app_model: AppModel) -> ViewPlugin:
        return ViewPlugin(app_model=app_model)

    def create_plot_plugin(self, app_model: AppModel) -> PlotPlugin:
        return PlotPlugin(app_model=app_model)


OBSTACLE_BILATERATION_PLUGIN = PluginSpec(
    generation=PluginGeneration.A121,
    key="obstacle_bilateration",
    title="Obstacle Bilateration",
    description="Use two sensors to estimate distance and two angles.",
    family=PluginFamily.EXAMPLE_APP,
    presets=[
        PluginPresetBase(name="Default", preset_id=PluginPresetId.DEFAULT),
    ],
    default_preset_id=PluginPresetId.DEFAULT,
)
