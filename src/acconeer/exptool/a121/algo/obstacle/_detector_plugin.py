# Copyright (c) Acconeer AB, 2023-2025
# All rights reserved

from __future__ import annotations

import logging
from enum import Enum, auto
from typing import Callable, Mapping, Optional

import attrs
import h5py
import numpy as np

from PySide6.QtGui import QTransform
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121, opser
from acconeer.exptool._core.docstrings import get_attribute_docstring
from acconeer.exptool.a121._h5_utils import _create_h5_string_dataset
from acconeer.exptool.a121.algo import PeakSortingMethod
from acconeer.exptool.a121.algo._plugins import (
    A121BackendPluginBase,
    A121ViewPluginBase,
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
    PidgetFactoryMapping,
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
from acconeer.exptool.app.new.ui.components.a121 import SensorConfigEditor

from ._detector import (
    DetailedStatus,
    Detector,
    DetectorConfig,
    DetectorContext,
    DetectorResult,
    _load_algo_data,
)


log = logging.getLogger(__name__)


@attrs.mutable(kw_only=True)
class SharedState:
    sensor_ids: list[int] = attrs.field(factory=lambda: [1])
    config: DetectorConfig = attrs.field(factory=DetectorConfig)
    context: DetectorContext = attrs.field(factory=DetectorContext)


class PluginPresetId(Enum):
    DEFAULT = auto()


@attrs.frozen(kw_only=True)
class SetupMessage(GeneralMessage):
    name: str = attrs.field(default="setup", init=False)
    recipient: backend.RecipientLiteral = attrs.field(default="plot_plugin", init=False)


class BackendPlugin(A121BackendPluginBase[SharedState]):
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
        self.shared_state.context = opser.deserialize(file["context"], DetectorContext)

    @is_task
    def restore_defaults(self) -> None:
        self.shared_state = SharedState()
        self.broadcast()

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
        self.broadcast()

    def save_to_cache(self, file: h5py.File) -> None:
        _create_h5_string_dataset(file, "config", self.shared_state.config.to_json())
        opser.serialize(self.shared_state.context, file.create_group("context"))

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
        self.callback(SetupMessage())

    def end_session(self) -> None:
        assert self._detector_instance
        if self._recorder is not None:
            self._recorder.close()
        self._detector_instance.stop()

    def get_next(self) -> None:
        if self._detector_instance is None:
            raise RuntimeError

        assert self.client
        result = self._detector_instance.get_next()

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
            self._detector_instance = Detector(
                client=self.client,
                sensor_ids=self.shared_state.sensor_ids,
                detector_config=self.shared_state.config,
                context=None,
            )
            self._detector_instance.calibrate_detector()
        except Exception as exc:
            msg = "Failed to calibrate detector"
            raise HandledException(msg) from exc
        finally:
            self.callback(PluginStateMessage(state=PluginState.LOADED_IDLE))

        self.shared_state.context = self._detector_instance.context
        self.broadcast()


class PlotPlugin(PgPlotPlugin):
    _PLOT_HISTORY_FRAMES = 50

    def __init__(self, app_model: AppModel) -> None:
        super().__init__(app_model=app_model)
        self._plot_job: Optional[DetectorResult] = None
        self._is_setup = False

    def handle_message(self, message: backend.GeneralMessage) -> None:
        if isinstance(message, backend.PlotMessage):
            self._plot_job = message.result
        elif isinstance(message, SetupMessage):
            self.setup()
            self._is_setup = True
        else:
            log.warn(f"{self.__class__.__name__} got an unsupported command: {message.name!r}.")

    def draw(self) -> None:
        if not self._is_setup or self._plot_job is None:
            return

        try:
            self.draw_plot_job(multi_sensor_result=self._plot_job)
        finally:
            self._plot_job = None

    def setup(self) -> None:
        self.plot_layout.clear()

        self.obst_vel_ys = [np.nan * np.ones(self._PLOT_HISTORY_FRAMES)]
        self.obst_dist_ys = [np.nan * np.ones(self._PLOT_HISTORY_FRAMES)]
        self.hist_x = np.linspace(
            -100, 0, self._PLOT_HISTORY_FRAMES
        )  # TODO: should no be hard coded

        # Upper row
        win = self.plot_layout
        win.setWindowTitle("Acconeer obstacle detector example")

        self.fftmap_plot = pg.PlotItem(title="FFT Map")
        self.fftmap_image = pg.ImageItem(autoDownsample=True)
        self.fftmap_image.setLookupTable(et.utils.pg_mpl_cmap("viridis"))

        self.fftmap_plot.setLabel("bottom", "Distance (m)")
        self.fftmap_plot.setLabel("left", "Velocity (cm/s)")
        self.fftmap_plot.addItem(self.fftmap_image)

        sublayout = win.addLayout(
            row=0,
            col=0,
            colspan=2,
        )
        sublayout.layout.setColumnStretchFactor(0, 2)
        sublayout.addItem(self.fftmap_plot, row=0, col=0)

        # Middle row

        self.bin0_plot = win.addPlot(
            row=1,
            col=0,
            title="Static objects (Zeroth FFT bin)",
        )

        self.bin0_plot.showGrid(x=True, y=True)
        self.bin0_plot.setLabel("bottom", "Range (cm)")
        self.bin0_plot.setLabel("left", "Amplitude")
        # self.bin0_plot.setXRange(0, 0)
        self.bin0_plot.addLegend()
        self.bin0_curves = [self.bin0_plot.plot(symbolSize=5, symbol="o")]

        pen = et.utils.pg_pen_cycler(0)
        brush = et.utils.pg_brush_cycler(0)
        symbol_kw = dict(symbol="o", symbolSize=1, symbolBrush=brush, symbolPen="k")
        feat_kw = dict(pen=pen, **symbol_kw)
        self.bin0_curve = self.bin0_plot.plot(**feat_kw)

        pen = et.utils.pg_pen_cycler(1)
        brush = et.utils.pg_brush_cycler(1)
        symbol_kw = dict(symbol="o", symbolSize=1, symbolBrush=brush, symbolPen="k")
        feat_kw = dict(pen=pen, **symbol_kw)
        self.bin0_threshold_curve = self.bin0_plot.plot(**feat_kw)

        bin0_plot_legend = pg.LegendItem(offset=(0.0, 0.45))
        bin0_plot_legend.setParentItem(self.bin0_plot)
        bin0_plot_legend.addItem(self.bin0_curve, "Sweep")
        bin0_plot_legend.addItem(self.bin0_threshold_curve, "Threshold")

        self.other_bins_plot = win.addPlot(
            row=1,
            col=1,
            title="Moving objects (Other FFT bins)",
        )

        self.other_bins_plot.showGrid(x=True, y=True)
        self.other_bins_plot.setLabel("bottom", "Range (cm)")
        self.other_bins_plot.setLabel("left", "Amplitude")
        # self.other_bins_plot.setXRange(0, 0)
        self.other_bins_plot.addLegend()
        self.other_bins_curves = [self.other_bins_plot.plot(symbolSize=5, symbol="o")]

        pen = et.utils.pg_pen_cycler(0)
        brush = et.utils.pg_brush_cycler(0)
        symbol_kw = dict(symbol="o", symbolSize=1, symbolBrush=brush, symbolPen="k")
        feat_kw = dict(pen=pen, **symbol_kw)
        self.other_bins_curve = self.other_bins_plot.plot(**feat_kw)

        pen = et.utils.pg_pen_cycler(1)
        brush = et.utils.pg_brush_cycler(1)
        symbol_kw = dict(symbol="o", symbolSize=1, symbolBrush=brush, symbolPen="k")
        feat_kw = dict(pen=pen, **symbol_kw)
        self.other_bins_threshold_curve = self.other_bins_plot.plot(**feat_kw)

        other_bins_plot_legend = pg.LegendItem(offset=(0.0, 0.45))
        other_bins_plot_legend.setParentItem(self.other_bins_plot)
        other_bins_plot_legend.addItem(self.other_bins_curve, "Sweep")
        other_bins_plot_legend.addItem(self.other_bins_threshold_curve, "Threshold")

        # Lower row

        self.angle_hist_plot = win.addPlot(
            row=2,
            col=0,
            title="Obstacle velocity history",
        )

        self.angle_hist_plot.showGrid(x=True, y=True)
        self.angle_hist_plot.setLabel("bottom", "Time (frames)")
        self.angle_hist_plot.setLabel("left", "Velocity (cm/s)")
        self.angle_hist_plot.setXRange(-100, 0)
        self.angle_hist_plot.addLegend()
        self.velocity_hist_curves = [self.angle_hist_plot.plot(symbolSize=5, symbol="o")]

        self.range_hist_plot = win.addPlot(
            row=2,
            col=1,
            title="Obstacle range history",
        )

        self.range_hist_plot.showGrid(x=True, y=True)
        self.range_hist_plot.setLabel("bottom", "Time (frames)")
        self.range_hist_plot.setLabel("left", "Range (cm)")
        self.range_hist_plot.setXRange(-100, 0)
        self.range_hist_plot.addLegend()
        self.range_hist_curves = [self.range_hist_plot.plot(symbolSize=5, symbol="o")]

        close_proximity_html = (
            '<p style="text-align: center; color: white; font-size: 10pt;">{}</p>'.format(
                "Close proximity detection",
            )
        )

        self.close_proximity_text_item = pg.TextItem(
            html=close_proximity_html,
            fill=pg.mkColor(0xFF, 0x7F, 0x0E),
            anchor=(0.5, 0),
        )
        self.range_hist_plot.addItem(self.close_proximity_text_item)
        self.close_proximity_text_item.hide()

    def draw_plot_job(self, multi_sensor_result: DetectorResult) -> None:
        # Get the first element as the plugin only supports single sensor operation.

        (pr,) = multi_sensor_result.processor_results.values()
        er = pr.subsweeps_extra_results[0]

        fftmap = er.fft_map
        fftmap_threshold = er.fft_map_threshold
        spf = fftmap.shape[0]

        transform = QTransform()
        transform.translate(
            100 * er.r[0], -100 * pr.extra_result.dv * spf / 2 - 0.5 * 100 * pr.extra_result.dv
        )
        transform.scale(100 * er.r[1] - 100 * er.r[0], 100 * pr.extra_result.dv)

        self.fftmap_image.setTransform(transform)
        self.fftmap_image.updateImage(
            np.fft.fftshift(fftmap, 0).T,
            levels=(0, 1.05 * np.max(fftmap)),
        )

        bin0 = fftmap[0, :]
        threshold_bin0 = fftmap_threshold[0, :]

        max_other_bins = np.max(fftmap[1:, :], axis=0)
        threshold_other_bins = fftmap_threshold[1, :]

        self.bin0_curve.setData(100 * er.r, bin0)
        self.bin0_threshold_curve.setData(100 * er.r, threshold_bin0)
        self.other_bins_curve.setData(100 * er.r, max_other_bins)
        self.other_bins_threshold_curve.setData(100 * er.r, threshold_other_bins)

        self.angle_hist_plot.setYRange(
            -100 * pr.extra_result.dv * spf / 2, 100 * pr.extra_result.dv * spf / 2
        )
        v = pr.targets[0].velocity if pr.targets else np.nan

        self.obst_vel_ys[0] = np.roll(self.obst_vel_ys[0], -1)
        self.obst_vel_ys[0][-1] = 100 * v  # m/s -> cm/s

        if np.isnan(self.obst_vel_ys[0]).all():
            self.velocity_hist_curves[0].setVisible(False)
        else:
            self.velocity_hist_curves[0].setVisible(True)
            self.velocity_hist_curves[0].setData(
                self.hist_x, self.obst_vel_ys[0], connect="finite"
            )

        min_range = 100 * er.r[0]
        max_range = 100 * er.r[-1]
        self.range_hist_plot.setYRange(min_range, max_range)
        r = pr.targets[0].distance if pr.targets else np.nan

        self.obst_dist_ys[0] = np.roll(self.obst_dist_ys[0], -1)
        self.obst_dist_ys[0][-1] = 100 * r  # m/s -> cm/s

        if np.isnan(self.obst_dist_ys[0]).all():
            self.range_hist_curves[0].setVisible(False)
        else:
            self.range_hist_curves[0].setVisible(True)
            self.range_hist_curves[0].setData(self.hist_x, self.obst_dist_ys[0], connect="finite")

        if multi_sensor_result.close_proximity_trig:
            close_prox = list(multi_sensor_result.close_proximity_trig.values())
            self.range_hist_plot.getAxis("left")
            self.close_proximity_text_item.setPos(-50, max_range)
            self.close_proximity_text_item.setVisible(close_prox[0])


class ViewPlugin(A121ViewPluginBase):
    sensor_config_editors: list[SensorConfigEditor]

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

        self.misc_error_view = MiscErrorView(self.scrolly_widget)
        scrolly_layout.addWidget(self.misc_error_view)

        sensor_selection_group = GroupBox.vertical("Sensor selection", parent=self.scrolly_widget)
        self.sensor_id_pidget = pidgets.SensorIdPidgetFactory(items=[]).create(
            parent=sensor_selection_group
        )
        self.sensor_id_pidget.sig_update.connect(self._on_sensor_id_update)
        sensor_selection_group.layout().addWidget(self.sensor_id_pidget)
        scrolly_layout.addWidget(sensor_selection_group)

        self.config_editor = AttrsConfigEditor[DetectorConfig](
            title="Detector parameters",
            config_type=DetectorConfig,
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
            "start_m": pidgets.FloatPidgetFactory(
                name_label_text="Range start:",
                name_label_tooltip=get_attribute_docstring(DetectorConfig, "start_m"),
                suffix=" m",
                decimals=3,
            ),
            "end_m": pidgets.FloatPidgetFactory(
                name_label_text="Range end:",
                name_label_tooltip=get_attribute_docstring(DetectorConfig, "end_m"),
                suffix=" m",
                decimals=3,
            ),
            "step_length": pidgets.IntPidgetFactory(
                name_label_text="Step length (in unit 2.5 mm):",
                name_label_tooltip=get_attribute_docstring(DetectorConfig, "step_length"),
                suffix=" ",
            ),
            "max_robot_speed": pidgets.FloatPidgetFactory(
                name_label_text="Max robot speed:",
                name_label_tooltip=get_attribute_docstring(DetectorConfig, "max_robot_speed"),
                suffix=" m/s",
                limits=(0.001, None),
                decimals=3,
            ),
            "profile": pidgets.EnumPidgetFactory(
                name_label_text="Profile:",
                name_label_tooltip=get_attribute_docstring(DetectorConfig, "profile"),
                enum_type=a121.Profile,
                label_mapping={
                    a121.Profile.PROFILE_1: "1 (best resolution)",
                    a121.Profile.PROFILE_2: "2",
                    a121.Profile.PROFILE_3: "3",
                    a121.Profile.PROFILE_4: "4",
                    a121.Profile.PROFILE_5: "5 (best SNR)",
                },
            ),
            "hwaas": pidgets.IntPidgetFactory(
                name_label_text="Hardware averaging (HWAAS):",
                name_label_tooltip=get_attribute_docstring(DetectorConfig, "hwaas"),
                suffix=" ",
            ),
            "num_std_threshold": pidgets.FloatPidgetFactory(
                name_label_text="Noise threshold:",
                name_label_tooltip=get_attribute_docstring(DetectorConfig, "num_std_threshold"),
                suffix=" ",
                decimals=3,
            ),
            "num_mean_threshold": pidgets.FloatPidgetFactory(
                name_label_text="Mean threshold:",
                name_label_tooltip=get_attribute_docstring(DetectorConfig, "num_mean_threshold"),
                suffix=" ",
                decimals=3,
            ),
            "num_frames_in_recorded_threshold": pidgets.IntPidgetFactory(
                name_label_text="Nbr frames used to determine treshold:",
                name_label_tooltip=get_attribute_docstring(
                    DetectorConfig, "num_frames_in_recorded_threshold"
                ),
                suffix=" ",
            ),
            "sweeps_per_frame": pidgets.IntPidgetFactory(
                name_label_text="Number of sweeps per frame:",
                name_label_tooltip=get_attribute_docstring(DetectorConfig, "sweeps_per_frame"),
                suffix=" ",
            ),
            "update_rate": pidgets.FloatPidgetFactory(
                name_label_text="Detector update rate:",
                name_label_tooltip=get_attribute_docstring(DetectorConfig, "update_rate"),
                suffix=" Hz",
                decimals=1,
            ),
            "peak_sorting_method": pidgets.EnumPidgetFactory(
                name_label_text="Peak sorting method:",
                name_label_tooltip=get_attribute_docstring(DetectorConfig, "peak_sorting_method"),
                enum_type=PeakSortingMethod,
                label_mapping={
                    PeakSortingMethod.CLOSEST: "Closest",
                    PeakSortingMethod.STRONGEST: "Strongest",
                },
            ),
            "dead_reckoning_duration_s": pidgets.FloatPidgetFactory(
                name_label_text="Dead reckoning duration:",
                name_label_tooltip=get_attribute_docstring(
                    DetectorConfig, "dead_reckoning_duration_s"
                ),
                suffix=" s",
                decimals=1,
            ),
            "kalman_sensitivity": pidgets.FloatSliderPidgetFactory(
                name_label_text="Kalman filter sensitivity:",
                name_label_tooltip=get_attribute_docstring(DetectorConfig, "kalman_sensitivity"),
                decimals=2,
                limits=(0.001, 1),
                show_limit_values=False,
                limit_texts=("Higher robustness", "More Responsive"),
            ),
            "enable_close_proximity_detection": pidgets.CheckboxPidgetFactory(
                name_label_text="Enable close proximity detection",
                name_label_tooltip=get_attribute_docstring(
                    DetectorConfig, "enable_close_proximity_detection"
                ),
            ),
        }

    def on_backend_state_update(self, state: Optional[SharedState]) -> None:
        if state is None:
            self.config_editor.set_data(None)
            self.message_box.setText("")
        else:
            self.config_editor.set_data(state.config)

            detector_status = Detector.get_detector_status(
                state.config, state.context, state.sensor_ids
            )

            self.message_box.setText(self.TEXT_MSG_MAP[detector_status.detector_state])

            validation_results = state.config._collect_validation_results()

            not_handled = self.config_editor.handle_validation_results(validation_results)
            not_handled = self.misc_error_view.handle_validation_results(not_handled)
            assert not_handled == []

    def on_app_model_update(self, app_model: AppModel) -> None:
        self.sensor_id_pidget.set_selectable_sensors(app_model.connected_sensors)

        visual_policies.apply_enabled_policy(
            visual_policies.config_editor_enabled,
            app_model,
            widgets=[
                self.defaults_button,
                self.config_editor,
                self.sensor_id_pidget,
            ],
        )
        self.stop_button.setEnabled(visual_policies.stop_button_enabled(app_model))

        state = app_model.backend_plugin_state

        if state is None:
            ready_to_start = False
            config_valid = False
        else:
            detector_status = Detector.get_detector_status(
                state.config, state.context, state.sensor_ids
            )

            ready_to_start = detector_status.ready_to_start
            config_valid = self._config_valid(state) and self.config_editor.is_ready

        self.calibrate_detector_button.setEnabled(
            visual_policies.start_button_enabled(app_model, extra_condition=config_valid),
        )
        self.start_button.setEnabled(
            visual_policies.start_button_enabled(
                app_model, extra_condition=ready_to_start and config_valid
            )
        )

    def _config_valid(self, state: SharedState) -> bool:
        try:
            state.config.validate()
        except a121.ValidationResult:
            return False
        else:
            return True

    def _on_sensor_id_update(self, sensor_id: int) -> None:
        BackendPlugin.update_sensor_ids.rpc(self.app_model.put_task, sensor_ids=[sensor_id])

    def _on_config_update(self, config: DetectorConfig) -> None:
        BackendPlugin.update_config.rpc(self.app_model.put_task, config=config)

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


OBSTACLE_DETECTOR_PLUGIN = PluginSpec(
    generation=PluginGeneration.A121,
    key="obstacle_detector",
    title="Obstacle detection",
    docs_link="https://docs.acconeer.com/en/latest/example_apps/a121/obstacle_detection.html",
    description="Measure distance and angle to objects from a moving platform.",
    family=PluginFamily.EXAMPLE_APP,
    presets=[
        PluginPresetBase(name="Default", preset_id=PluginPresetId.DEFAULT),
    ],
    default_preset_id=PluginPresetId.DEFAULT,
)
