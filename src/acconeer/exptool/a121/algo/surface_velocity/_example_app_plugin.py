# Copyright (c) Acconeer AB, 2023-2024
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
from acconeer.exptool.app.new.ui.components.a121 import RangeHelpView

from ._example_app import ExampleApp, ExampleAppConfig, ExampleAppResult, _load_algo_data


log = logging.getLogger(__name__)


@attrs.mutable(kw_only=True)
class SharedState:
    sensor_id: int = attrs.field(default=1)
    config: ExampleAppConfig = attrs.field(factory=ExampleAppConfig)


class PluginPresetId(Enum):
    DEFAULT = auto()


@attrs.frozen(kw_only=True)
class SetupMessage(GeneralMessage):
    example_app_config: ExampleAppConfig
    name: str = attrs.field(default="setup", init=False)
    recipient: backend.RecipientLiteral = attrs.field(default="plot_plugin", init=False)


class BackendPlugin(A121BackendPluginBase[SharedState]):
    PLUGIN_PRESETS: Mapping[int, Callable[[], ExampleAppConfig]] = {
        PluginPresetId.DEFAULT.value: lambda: ExampleAppConfig()
    }

    def __init__(
        self, callback: Callable[[Message], None], generation: PluginGeneration, key: str
    ) -> None:
        super().__init__(callback=callback, generation=generation, key=key)

        self._recorder: Optional[a121.H5Recorder] = None
        self._exempel_app_instance: Optional[ExampleApp] = None
        self._log = BackendLogger.getLogger(__name__)

        self.restore_defaults()

    def _load_from_cache(self, file: h5py.File) -> None:
        self.shared_state.config = ExampleAppConfig.from_json(file["config"][()])

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
    def update_config(self, *, config: ExampleAppConfig) -> None:
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
        self._example_app_instance = ExampleApp(
            client=self.client,
            sensor_id=self.shared_state.sensor_id,
            example_app_config=self.shared_state.config,
        )
        self._example_app_instance.start(recorder)
        self.callback(SetupMessage(example_app_config=self.shared_state.config))

    def end_session(self) -> None:
        if self._example_app_instance is None:
            raise RuntimeError
        if self._recorder is not None:
            self._recorder.close()
        self._example_app_instance.stop()

    def get_next(self) -> None:
        assert self.client
        if self._example_app_instance is None:
            raise RuntimeError
        result = self._example_app_instance.get_next()

        self.callback(backend.PlotMessage(result=result))


class PlotPlugin(PgPlotPlugin):
    _VELOCITY_Y_SCALE_MARGIN_M = 0.25

    def __init__(self, app_model: AppModel) -> None:
        super().__init__(app_model=app_model)
        self._plot_job: Optional[ExampleAppResult] = None
        self._is_setup = False

    def handle_message(self, message: backend.GeneralMessage) -> None:
        if isinstance(message, backend.PlotMessage):
            if not isinstance(message.result, ExampleAppResult):
                msg = f"Unexpected result type: {type(message.result)}"
                raise RuntimeError(msg)

            self._plot_job = message.result
        elif isinstance(message, SetupMessage):
            self.setup(example_app_config=message.example_app_config)
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
        example_app_config: ExampleAppConfig,
    ) -> None:
        self.plot_layout.clear()

        self.slow_zone = example_app_config.slow_zone
        self.history_length_s = 10
        if example_app_config.frame_rate is None:
            estimated_frame_rate = (
                example_app_config.sweep_rate / example_app_config.sweeps_per_frame
            )
        else:
            estimated_frame_rate = example_app_config.frame_rate

        self.history_length_n = int(np.around(self.history_length_s * estimated_frame_rate))

        c0_dashed_pen = et.utils.pg_pen_cycler(0, width=2.5, style="--")

        # Velocity plot

        self.velocity_history_plot = self._create_plot(self.plot_layout, row=0, col=0)
        self.velocity_history_plot.setTitle("Estimated velocity")
        self.velocity_history_plot.setLabel(axis="left", text="Velocity", units="m/s")
        self.velocity_history_plot.setLabel(axis="bottom", text="Time", units="s")
        self.velocity_history_plot.addLegend(labelTextSize="10pt")
        self.velocity_smooth_limits = et.utils.SmoothLimits()

        self.velocity_curve = self.velocity_history_plot.plot(
            pen=et.utils.pg_pen_cycler(0), name="Estimated velocity"
        )

        self.psd_html = (
            '<div style="text-align: center">'
            '<span style="color: #FFFFFF;font-size:13pt;">'
            "{}</span></div>"
        )

        self.distance_text_item = pg.TextItem(
            html=self.psd_html,
            fill=pg.mkColor(0x1F, 0x77, 0xB4, 180),
            anchor=(0.5, 0),
        )

        self.velocity_history_plot.addItem(self.distance_text_item)

        self.velocity_history = np.zeros(self.history_length_n)

        self.lower_std_history = np.zeros(self.history_length_n)
        self.upper_std_history = np.zeros(self.history_length_n)

        self.lower_std_curve = self.velocity_history_plot.plot()
        self.upper_std_curve = self.velocity_history_plot.plot()

        fbi = pg.FillBetweenItem(
            self.lower_std_curve,
            self.upper_std_curve,
            brush=pg.mkBrush(f"{et.utils.color_cycler(0)}50"),
        )

        self.velocity_history_plot.addItem(fbi)

        # PSD plot

        self.psd_plot = self._create_plot(self.plot_layout, row=1, col=0)
        self.psd_plot.setTitle("PSD<br>(colored area represents the slow zone)")
        self.psd_plot.setLabel(axis="left", text="Power")
        self.psd_plot.setLabel(axis="bottom", text="Velocity", units="m/s")
        self.psd_plot.addLegend(labelTextSize="10pt")

        self.psd_smooth_max = et.utils.SmoothMax(tau_grow=0.5, tau_decay=2.0)
        self.psd_curve = self.psd_plot.plot(pen=et.utils.pg_pen_cycler(0), name="PSD")
        self.psd_threshold = self.psd_plot.plot(pen=c0_dashed_pen, name="Threshold")

        psd_slow_zone_color = et.utils.color_cycler(0)
        psd_slow_zone_color = f"{psd_slow_zone_color}50"
        psd_slow_zone_brush = pg.mkBrush(psd_slow_zone_color)

        self.psd_slow_zone = pg.LinearRegionItem(brush=psd_slow_zone_brush, movable=False)
        self.psd_plot.addItem(self.psd_slow_zone)

        brush = et.utils.pg_brush_cycler(0)
        self.psd_peak_plot_item = pg.PlotDataItem(
            pen=None, symbol="o", symbolSize=8, symbolBrush=brush, symbolPen="k"
        )
        self.psd_plot.addItem(self.psd_peak_plot_item)

        self.psd_plot.setLogMode(x=False, y=True)

    def draw_plot_job(self, example_app_result: ExampleAppResult) -> None:
        processor_extra_result = example_app_result.processor_extra_result

        lim = self.velocity_smooth_limits.update(example_app_result.velocity)

        self.velocity_history_plot.setYRange(
            lim[0] - self._VELOCITY_Y_SCALE_MARGIN_M, lim[1] + self._VELOCITY_Y_SCALE_MARGIN_M
        )
        self.velocity_history_plot.setXRange(-self.history_length_s, 0)

        xs = np.linspace(-self.history_length_s, 0, self.history_length_n)

        self.velocity_history = np.roll(self.velocity_history, -1)
        self.velocity_history[-1] = example_app_result.velocity
        self.velocity_curve.setData(xs, self.velocity_history)

        velocity_html = self.psd_html.format(
            f"Distance {np.around(example_app_result.distance_m, 2)} m"
        )
        self.distance_text_item.setHtml(velocity_html)
        self.distance_text_item.setPos(
            -self.history_length_s / 2, lim[1] + self._VELOCITY_Y_SCALE_MARGIN_M
        )

        self.lower_std_history = np.roll(self.lower_std_history, -1)
        self.lower_std_history[-1] = (
            example_app_result.velocity + 0.5 * processor_extra_result.peak_width
        )
        self.lower_std_curve.setData(xs, self.lower_std_history)

        self.upper_std_history = np.roll(self.upper_std_history, -1)
        self.upper_std_history[-1] = (
            example_app_result.velocity - 0.5 * processor_extra_result.peak_width
        )
        self.upper_std_curve.setData(xs, self.upper_std_history)

        low_lim = np.minimum(
            np.min(processor_extra_result.psd_threshold), np.min(processor_extra_result.psd)
        )
        high_lim = self.psd_smooth_max.update(
            np.maximum(processor_extra_result.psd_threshold, processor_extra_result.psd)
        )
        self.psd_plot.setYRange(np.log10(low_lim), np.log10(high_lim))
        self.psd_plot.setXRange(
            processor_extra_result.max_bin_vertical_vs[0],
            processor_extra_result.max_bin_vertical_vs[-1],
        )
        self.psd_curve.setData(
            processor_extra_result.vertical_velocities, processor_extra_result.psd
        )
        self.psd_threshold.setData(
            processor_extra_result.vertical_velocities, processor_extra_result.psd_threshold
        )
        if processor_extra_result.peak_idx is not None:
            self.psd_peak_plot_item.setData(
                [processor_extra_result.vertical_velocities[processor_extra_result.peak_idx]],
                [processor_extra_result.psd[processor_extra_result.peak_idx]],
            )
        else:
            self.psd_peak_plot_item.clear()

        middle_idx = int(np.around(processor_extra_result.vertical_velocities.shape[0] / 2))
        self.psd_slow_zone.setRegion(
            [
                processor_extra_result.vertical_velocities[middle_idx - self.slow_zone],
                processor_extra_result.vertical_velocities[middle_idx + self.slow_zone],
            ]
        )

    @staticmethod
    def _create_plot(parent: pg.GraphicsLayout, row: int, col: int) -> pg.PlotItem:
        velocity_history_plot = parent.addPlot(row=row, col=col)
        velocity_history_plot.setMenuEnabled(False)
        velocity_history_plot.setMouseEnabled(x=False, y=False)
        velocity_history_plot.hideButtons()
        velocity_history_plot.showGrid(x=True, y=True, alpha=0.5)

        return velocity_history_plot


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

        self.range_helper = RangeHelpView()
        scrolly_layout.addWidget(self.range_helper)

        self.config_editor = AttrsConfigEditor(
            title="Example app parameters",
            factory_mapping=self._get_pidget_mapping(),
            config_type=ExampleAppConfig,
            parent=self.scrolly_widget,
        )
        self.config_editor.sig_update.connect(self._on_config_update)
        scrolly_layout.addWidget(self.config_editor)

        self.sticky_widget.setLayout(sticky_layout)
        self.scrolly_widget.setLayout(scrolly_layout)

    @classmethod
    def _get_pidget_mapping(cls) -> PidgetFactoryMapping:
        return {
            "surface_distance": pidgets.FloatPidgetFactory(
                name_label_text="Surface distance:",
                name_label_tooltip=get_attribute_docstring(ExampleAppConfig, "surface_distance"),
                suffix=" m",
                decimals=2,
                limits=(0.1, None),
            ),
            "sensor_angle": pidgets.FloatPidgetFactory(
                name_label_text="Sensor angle:",
                name_label_tooltip=get_attribute_docstring(ExampleAppConfig, "sensor_angle"),
                suffix=" degrees",
                decimals=1,
                limits=(0, 89),
            ),
            "num_points": pidgets.IntPidgetFactory(
                name_label_text="Number of distance points:",
                name_label_tooltip=get_attribute_docstring(ExampleAppConfig, "num_points"),
                limits=(1, None),
            ),
            "sweep_rate": pidgets.FloatPidgetFactory(
                name_label_text="Sweep rate:",
                name_label_tooltip=get_attribute_docstring(ExampleAppConfig, "sweep_rate"),
                suffix=" Hz",
                decimals=1,
                limits=(100, None),
            ),
            "sweeps_per_frame": pidgets.IntPidgetFactory(
                name_label_text="Sweeps per frame:",
                name_label_tooltip=get_attribute_docstring(ExampleAppConfig, "sweeps_per_frame"),
                limits=(64, 2048),
            ),
            "hwaas": pidgets.IntPidgetFactory(
                name_label_text="HWAAS:",
                name_label_tooltip=get_attribute_docstring(ExampleAppConfig, "hwaas"),
                limits=(1, 511),
            ),
            "profile": pidgets.OptionalEnumPidgetFactory(
                name_label_text="Profile:",
                name_label_tooltip=get_attribute_docstring(ExampleAppConfig, "profile"),
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
            "step_length": pidgets.IntPidgetFactory(
                name_label_text="Step length:",
                name_label_tooltip=get_attribute_docstring(ExampleAppConfig, "step_length"),
                limits=(1, None),
            ),
            "frame_rate": pidgets.OptionalFloatPidgetFactory(
                name_label_text="Frame rate:",
                name_label_tooltip=get_attribute_docstring(ExampleAppConfig, "frame_rate"),
                checkbox_label_text="Limit",
                suffix=" Hz",
                decimals=1,
                limits=(1, None),
                init_set_value=10,
            ),
            "continuous_sweep_mode": pidgets.CheckboxPidgetFactory(
                name_label_text="Continuos sweep mode",
                name_label_tooltip=get_attribute_docstring(
                    ExampleAppConfig, "continuous_sweep_mode"
                ),
            ),
            "double_buffering": pidgets.CheckboxPidgetFactory(
                name_label_text="Double buffering",
                name_label_tooltip=get_attribute_docstring(ExampleAppConfig, "double_buffering"),
            ),
            "inter_frame_idle_state": pidgets.EnumPidgetFactory(
                enum_type=a121.IdleState,
                name_label_text="Inter frame idle state:",
                name_label_tooltip=get_attribute_docstring(  # type: ignore[arg-type]
                    ExampleAppConfig, "inter_frame_idle_state"
                ),
                label_mapping={
                    a121.IdleState.DEEP_SLEEP: "Deep sleep",
                    a121.IdleState.SLEEP: "Sleep",
                    a121.IdleState.READY: "Ready",
                },
            ),
            "inter_sweep_idle_state": pidgets.EnumPidgetFactory(
                enum_type=a121.IdleState,
                name_label_text="Inter sweep idle state:",
                name_label_tooltip=get_attribute_docstring(  # type: ignore[arg-type]
                    ExampleAppConfig, "inter_sweep_idle_state"
                ),
                label_mapping={
                    a121.IdleState.DEEP_SLEEP: "Deep sleep",
                    a121.IdleState.SLEEP: "Sleep",
                    a121.IdleState.READY: "Ready",
                },
            ),
            "time_series_length": pidgets.IntPidgetFactory(
                name_label_text="Time series length:",
                name_label_tooltip=get_attribute_docstring(ExampleAppConfig, "time_series_length"),
                limits=(64, None),
            ),
            "psd_lp_coeff": pidgets.FloatSliderPidgetFactory(
                name_label_text="PSD time filtering coeff.:",
                name_label_tooltip=get_attribute_docstring(ExampleAppConfig, "psd_lp_coeff"),
                limits=(0, 1),
                decimals=3,
            ),
            "slow_zone": pidgets.IntPidgetFactory(
                name_label_text="Slow zone half length:",
                name_label_tooltip=get_attribute_docstring(ExampleAppConfig, "slow_zone"),
                limits=(0, 20),
            ),
            "velocity_lp_coeff": pidgets.FloatSliderPidgetFactory(
                name_label_text="Velocity time filtering coeff.\nper time series:",
                name_label_tooltip=get_attribute_docstring(ExampleAppConfig, "velocity_lp_coeff"),
                limits=(0, 1),
                decimals=3,
            ),
            "cfar_win": pidgets.IntPidgetFactory(
                name_label_text="CFAR window length:",
                name_label_tooltip=get_attribute_docstring(ExampleAppConfig, "cfar_win"),
                limits=(0, 20),
            ),
            "cfar_guard": pidgets.IntPidgetFactory(
                name_label_text="CFAR guard length:",
                name_label_tooltip=get_attribute_docstring(ExampleAppConfig, "cfar_guard"),
                limits=(0, 20),
            ),
            "cfar_sensitivity": pidgets.FloatSliderPidgetFactory(
                name_label_text="Threshold sensitivity:",
                name_label_tooltip=get_attribute_docstring(ExampleAppConfig, "cfar_sensitivity"),
                decimals=2,
                limits=(0.01, 1),
            ),
            "max_peak_interval_s": pidgets.FloatPidgetFactory(
                name_label_text="Max peak interval:",
                name_label_tooltip=get_attribute_docstring(
                    ExampleAppConfig, "max_peak_interval_s"
                ),
                decimals=1,
                limits=(0, 20),
                suffix=" s",
            ),
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

            self.range_helper.set_data(ExampleApp._get_sensor_config(state.config).subsweep)

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

    def _on_config_update(self, config: ExampleAppConfig) -> None:
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


SURFACE_VELOCITY_PLUGIN = PluginSpec(
    generation=PluginGeneration.A121,
    key="surface_velocity",
    title="Surface velocity",
    docs_link="https://docs.acconeer.com/en/latest/example_apps/a121/surface_velocity.html",
    description="Estimate surface speed and direction of streaming water.",
    family=PluginFamily.EXAMPLE_APP,
    presets=[
        PluginPresetBase(name="Default", preset_id=PluginPresetId.DEFAULT),
    ],
    default_preset_id=PluginPresetId.DEFAULT,
)
