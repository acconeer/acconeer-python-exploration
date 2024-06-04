# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved

from __future__ import annotations

import logging
from enum import Enum, auto
from typing import Callable, Mapping, Optional

import attrs
import h5py
import numpy as np

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
from acconeer.exptool.a121.algo._utils import estimate_frame_rate
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
    RangeHelpView,
    SensorConfigEditor,
)
from acconeer.exptool.app.new.ui.components.json_save_load_buttons import (
    JsonButtonOperations,
)
from acconeer.exptool.app.new.ui.stream_tab.plugin_widget import PluginPlotArea

from ._configs import get_default_config, get_traffic_config
from ._detector import (
    Detector,
    DetectorConfig,
    DetectorMetadata,
    DetectorResult,
    _load_algo_data,
)


log = logging.getLogger(__name__)


@attrs.mutable(kw_only=True)
class SharedState:
    sensor_id: int = attrs.field(default=1)
    config: DetectorConfig = attrs.field(factory=DetectorConfig)


class PluginPresetId(Enum):
    DEFAULT = auto()
    TRAFFIC = auto()


@attrs.frozen(kw_only=True)
class SetupMessage(GeneralMessage):
    detector_config: DetectorConfig
    detector_metadata: DetectorMetadata
    estimated_frame_rate: float
    name: str = attrs.field(default="setup", init=False)
    recipient: backend.RecipientLiteral = attrs.field(default="plot_plugin", init=False)


class BackendPlugin(A121BackendPluginBase[SharedState]):
    PLUGIN_PRESETS: Mapping[int, Callable[[], DetectorConfig]] = {
        PluginPresetId.DEFAULT.value: lambda: get_default_config(),
        PluginPresetId.TRAFFIC.value: lambda: get_traffic_config(),
    }

    def __init__(
        self,
        callback: Callable[[Message], None],
        generation: PluginGeneration,
        key: str,
    ) -> None:
        super().__init__(callback=callback, generation=generation, key=key)

        self._recorder: Optional[a121.H5Recorder] = None
        self._detector_instance: Optional[Detector] = None
        self._log = BackendLogger.getLogger(__name__)

        self.restore_defaults()

    def _load_from_cache(self, file: h5py.File) -> None:
        self.shared_state.config = DetectorConfig.from_json(file["config"][()])

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
    def update_config(self, *, config: DetectorConfig) -> None:
        self.shared_state.config = config
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
        _, config = _load_algo_data(algo_group)
        self.shared_state.config = config
        self.shared_state.sensor_id = record.sensor_id

    def _start_session(self, recorder: Optional[a121.H5Recorder]) -> None:
        assert self.client
        self._detector_instance = Detector(
            client=self.client,
            sensor_id=self.shared_state.sensor_id,
            detector_config=self.shared_state.config,
        )
        sensor_config = self._detector_instance._get_sensor_config(self._detector_instance.config)
        session_config = a121.SessionConfig(
            {self.shared_state.sensor_id: sensor_config},
            extended=False,
        )

        estimated_frame_rate = estimate_frame_rate(self.client, session_config)

        self._detector_instance.start(recorder)
        assert self._detector_instance.detector_metadata is not None
        self.callback(
            SetupMessage(
                detector_config=self.shared_state.config,
                detector_metadata=self._detector_instance.detector_metadata,
                estimated_frame_rate=estimated_frame_rate,
            )
        )

    def end_session(self) -> None:
        if self._detector_instance is None:
            raise RuntimeError
        self._detector_instance.stop()

    def get_next(self) -> None:
        assert self.client
        if self._detector_instance is None:
            raise RuntimeError
        result = self._detector_instance.get_next()

        self.callback(backend.PlotMessage(result=result))


class PlotPlugin(PgPlotPlugin):
    def __init__(self, app_model: AppModel) -> None:
        super().__init__(app_model=app_model)
        self._is_setup = False
        self._plot_job: Optional[DetectorResult] = None

    def handle_message(self, message: backend.GeneralMessage) -> None:
        if isinstance(message, backend.PlotMessage):
            self._plot_job = message.result
        elif isinstance(message, SetupMessage):
            self.setup(
                message.detector_config,
                message.detector_metadata,
                message.estimated_frame_rate,
            )
            self._is_setup = True
        else:
            log.warn(f"{self.__class__.__name__} got an unsupported command: {message.name!r}.")

    def draw(self) -> None:
        if not self._is_setup or self._plot_job is None:
            return

        try:
            self.draw_plot_job(self._plot_job)
        finally:
            self._plot_job = None

    def setup(
        self,
        detector_config: DetectorConfig,
        detector_metadata: DetectorMetadata,
        estimated_frame_rate: float,
    ) -> None:
        self.plot_layout.clear()

        self.detector_config = detector_config

        self.n_depths = detector_metadata.num_points

        max_update_rate = PluginPlotArea._FPS

        if estimated_frame_rate > max_update_rate:
            plugin_frame_rate = float(max_update_rate)
        else:
            plugin_frame_rate = estimated_frame_rate

        self.history_length_s = 10.0
        self.history_length = int(self.history_length_s * plugin_frame_rate)

        self.time_window_length_s = 3.0
        self.time_window_length_n = int(self.time_window_length_s * plugin_frame_rate)

        self.speed_history = np.zeros(self.history_length)
        self.speed_history_xs = np.array([i for i in range(-self.history_length, 0)])

        n_ticks_to_display = 10
        x_labels = np.linspace(-self.history_length_s, 0, self.history_length)
        all_ticks = [
            (t, "{:.0f}".format(label)) for t, label in zip(self.speed_history_xs, x_labels)
        ]
        subsample_step = self.history_length // n_ticks_to_display
        display_ticks = [all_ticks[::subsample_step]]

        win = self.plot_layout

        # FFT plot

        self.raw_fft_plot = win.addPlot(row=1, col=0)
        self.raw_fft_plot.setTitle("Frequency data")
        self.raw_fft_plot.setLabel(axis="left", text="Amplitude")
        self.raw_fft_plot.setLabel(axis="bottom", text="Frequency", units="Hz")
        self.raw_fft_plot.addLegend(labelTextSize="10pt")
        self.raw_fft_limits = et.utils.SmoothLimits()
        self.raw_fft_plot.setMenuEnabled(False)
        self.raw_fft_plot.setMouseEnabled(x=False, y=False)
        self.raw_fft_plot.hideButtons()
        self.raw_fft_plot.showGrid(x=True, y=True)
        self.raw_fft_plot.setLogMode(x=False, y=True)
        self.raw_fft_curves = []
        self.raw_fft_smooth_max = et.utils.SmoothMax(self.detector_config.frame_rate)
        self.raw_thresholds_curves = []

        for i in range(self.n_depths):
            raw_fft_curve = self.raw_fft_plot.plot(pen=et.utils.pg_pen_cycler(i), name="Fft")
            threshold_curve = self.raw_fft_plot.plot(
                pen=et.utils.pg_pen_cycler(i, style="--"), name="Threshold"
            )
            self.raw_fft_curves.append(raw_fft_curve)
            self.raw_thresholds_curves.append(threshold_curve)

        self.speed_history_plot = win.addPlot(row=0, col=0)
        self.speed_history_plot.setTitle("Speed history")
        self.speed_history_plot.setLabel(axis="left", text="Speed", units="m/s")
        self.speed_history_plot.setLabel(axis="bottom", text="Time", units="Seconds")
        self.speed_history_plot.addLegend(labelTextSize="10pt")
        self.speed_history_curve = self.speed_history_plot.plot(
            pen=None,
            name="speed",
            symbol="o",
            symbolsize=3,
        )

        if detector_config.sweep_rate is not None:
            actual_max_speed = detector_config._get_max_speed(detector_config.sweep_rate)
            self.speed_history_plot.setYRange(-actual_max_speed, actual_max_speed)
        else:
            self.speed_history_plot.setYRange(
                -detector_config.max_speed, detector_config.max_speed
            )
        self.speed_history_plot.setXRange(-self.history_length, 0)
        ay = self.speed_history_plot.getAxis("bottom")
        ay.setTicks(display_ticks)

        self.speed_html_format = (
            '<div style="text-align: center">'
            '<span style="color: #FFFFFF;font-size:15pt;">'
            "{}</span></div>"
        )

        self.speed_text_item = pg.TextItem(
            fill=pg.mkColor(0xFF, 0x7F, 0x0E, 200),
            anchor=(0.5, 0.5),
        )

        self.speed_text_item.setPos(-self.history_length / 2, -detector_config.max_speed / 2)
        brush = et.utils.pg_brush_cycler(1)
        self.speed_history_peak_plot_item = pg.PlotDataItem(
            pen=None, symbol="o", symbolSize=8, symbolBrush=brush, symbolPen="k"
        )
        self.speed_history_plot.addItem(self.speed_history_peak_plot_item)
        self.speed_history_plot.addItem(self.speed_text_item)

        self.speed_text_item.hide()

    def draw_plot_job(self, data: DetectorResult) -> None:
        psd = data.extra_result.psd
        speed_guess = data.max_speed
        x_speeds = data.extra_result.velocities
        thresholds = data.extra_result.actual_thresholds

        self.speed_history = np.roll(self.speed_history, -1)

        self.speed_history[-1] = speed_guess

        if self.time_window_length_n > 0:
            pos_speed = np.max(self.speed_history[-self.time_window_length_n :])
            pos_ind = int(np.argmax(self.speed_history[-self.time_window_length_n :]))
            neg_speed = np.min(self.speed_history[-self.time_window_length_n :])
            neg_ind = int(np.argmin(self.speed_history[-self.time_window_length_n :]))

            if abs(neg_speed) > abs(pos_speed):
                max_display_speed = neg_speed
                max_display_ind = neg_ind
            else:
                max_display_speed = pos_speed
                max_display_ind = pos_ind
        else:
            max_display_speed = self.speed_history[-1]
            max_display_ind = -1

        if max_display_speed != 0.0:
            speed_text = "Max speed estimate {:.4f} m/s".format(max_display_speed)
            speed_html = self.speed_html_format.format(speed_text)

            self.speed_text_item.setHtml(speed_html)
            self.speed_text_item.show()

            sub_xs = self.speed_history_xs[-self.time_window_length_n :]
            self.speed_history_peak_plot_item.setData(
                [sub_xs[max_display_ind]], [max_display_speed]
            )
        else:
            self.speed_history_peak_plot_item.clear()
            self.speed_text_item.hide()

        display_inds = np.array([i for i, x in enumerate(self.speed_history) if x != 0.0])
        if len(display_inds) > 0:
            display_xs = self.speed_history_xs[display_inds]
            display_data = self.speed_history[display_inds]
        else:
            display_xs = []
            display_data = []
        self.speed_history_curve.setData(display_xs, display_data)

        assert psd is not None
        assert thresholds is not None

        top_max = max(np.max(psd), np.max(thresholds))

        smooth_max_val = np.log10(self.raw_fft_smooth_max.update(top_max))
        self.raw_fft_plot.setYRange(-2, smooth_max_val)
        for i in range(psd.shape[1]):
            self.raw_fft_curves[i].setData(x_speeds, psd[:, i])

            threshold_line = np.full(x_speeds.shape[0], thresholds[i])
            self.raw_thresholds_curves[i].setData(x_speeds, threshold_line)


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

        self.config_editor = AttrsConfigEditor[DetectorConfig](
            title="Detector parameters",
            factory_mapping=self._get_pidget_mapping(),
            config_type=DetectorConfig,
            parent=self.scrolly_widget,
        )
        self.config_editor.sig_update.connect(self._on_config_update)

        self.range_help_view = RangeHelpView()
        scrolly_layout.addWidget(self.range_help_view)

        scrolly_layout.addWidget(self.config_editor)

        self.sensor_config_status = SensorConfigEditor(
            json_button_operations=JsonButtonOperations.SAVE
        )
        self.sensor_config_status.set_read_only(True)
        collapsible_widget = CollapsibleWidget(
            "Current sensor settings", self.sensor_config_status, self.scrolly_widget
        )
        scrolly_layout.addWidget(collapsible_widget)

        self.sticky_widget.setLayout(sticky_layout)
        self.scrolly_widget.setLayout(scrolly_layout)

    @classmethod
    def _get_pidget_mapping(cls) -> PidgetGroupFactoryMapping:
        service_parameters = {
            "start_point": pidgets.IntPidgetFactory(
                name_label_text="Start point:",
                name_label_tooltip=get_attribute_docstring(DetectorConfig, "start_point"),
            ),
            "num_points": pidgets.IntPidgetFactory(
                name_label_text="Number of points:",
                name_label_tooltip=get_attribute_docstring(DetectorConfig, "num_points"),
                limits=(1, 100),
            ),
            "step_length": pidgets.OptionalIntPidgetFactory(
                name_label_text="Step length:",
                name_label_tooltip=get_attribute_docstring(DetectorConfig, "step_length"),
                checkbox_label_text="Override",
                limits=(1, None),
                init_set_value=72,
            ),
            "profile": pidgets.OptionalEnumPidgetFactory(
                name_label_text="Profile:",
                name_label_tooltip=get_attribute_docstring(DetectorConfig, "profile"),
                checkbox_label_text="Override",
                enum_type=a121.Profile,
                label_mapping={
                    a121.Profile.PROFILE_1: "1 (shortest)",
                    a121.Profile.PROFILE_2: "2",
                    a121.Profile.PROFILE_3: "3",
                    a121.Profile.PROFILE_4: "4",
                    a121.Profile.PROFILE_5: "5 (longest)",
                },
            ),
            "sweep_rate": pidgets.OptionalIntPidgetFactory(
                name_label_text="Sweep rate:",
                name_label_tooltip=get_attribute_docstring(DetectorConfig, "sweep_rate"),
                suffix=" Hz",
                checkbox_label_text="Override",
                limits=(1, 134000),
                init_set_value=10000,
            ),
            "frame_rate": pidgets.OptionalFloatPidgetFactory(
                name_label_text="Frame rate:",
                name_label_tooltip=get_attribute_docstring(DetectorConfig, "frame_rate"),
                suffix=" Hz",
                checkbox_label_text="Override",
                limits=(1, 200),
                init_set_value=20.0,
            ),
            "hwaas": pidgets.OptionalIntPidgetFactory(
                name_label_text="HWAAS:",
                name_label_tooltip=get_attribute_docstring(DetectorConfig, "hwaas"),
                checkbox_label_text="Override",
                limits=(1, 511),
                init_set_value=4,
            ),
            "num_bins": pidgets.IntPidgetFactory(
                name_label_text="Number of bins:",
                name_label_tooltip=get_attribute_docstring(DetectorConfig, "num_bins"),
                limits=(3, 4095),
            ),
        }
        processing_parameters = {
            "max_speed": pidgets.FloatPidgetFactory(
                name_label_text="Max speed:",
                name_label_tooltip=get_attribute_docstring(DetectorConfig, "max_speed"),
                suffix=" m/s",
                limits=(0, 150.0),
            ),
            "threshold": pidgets.FloatPidgetFactory(
                name_label_text="Detection threshold:",
                name_label_tooltip=get_attribute_docstring(DetectorConfig, "threshold"),
                limits=(1.0, 10000.0),
            ),
        }
        return {
            pidgets.FlatPidgetGroup(): service_parameters,
            pidgets.FlatPidgetGroup(): processing_parameters,
        }

    def on_backend_state_update(self, state: Optional[SharedState]) -> None:
        if state is None:
            self.config_editor.set_data(None)
        else:
            self.config_editor.set_data(state.config)
            self.sensor_id_pidget.set_data(state.sensor_id)

            results = state.config._collect_validation_results()

            not_handled = self.config_editor.handle_validation_results(results)

            not_handled = self.misc_error_view.handle_validation_results(not_handled)

            assert not_handled == []

            sensor_config = Detector._get_sensor_config(state.config)
            self.range_help_view.set_data(sensor_config.subsweep)
            self.sensor_config_status.set_data(sensor_config)

    def on_app_model_update(self, app_model: AppModel) -> None:
        self.sensor_id_pidget.set_selectable_sensors(app_model.connected_sensors)

        visual_policies.apply_enabled_policy(
            visual_policies.config_editor_enabled,
            app_model,
            widgets=[self.config_editor, self.sensor_id_pidget],
        )

        self.start_button.setEnabled(
            visual_policies.start_button_enabled(
                app_model, extra_condition=self.config_editor.is_ready
            )
        )
        self.stop_button.setEnabled(visual_policies.stop_button_enabled(app_model))

    def _on_config_update(self, config: DetectorConfig) -> None:
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


SPEED_DETECTOR_PLUGIN = PluginSpec(
    generation=PluginGeneration.A121,
    key="speed_detector",
    title="Speed detector",
    docs_link="https://docs.acconeer.com/en/latest/detectors/a121/speed_detector.html",
    description="Measure speed.",
    family=PluginFamily.DETECTOR,
    presets=[
        PluginPresetBase(
            name="Default",
            description="Default settings to validate functionality",
            preset_id=PluginPresetId.DEFAULT,
        ),
        PluginPresetBase(
            name="Traffic",
            description="Settings to validate fast traffic",
            preset_id=PluginPresetId.TRAFFIC,
        ),
    ],
    default_preset_id=PluginPresetId.DEFAULT,
)
