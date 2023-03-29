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

from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121._h5_utils import _create_h5_string_dataset
from acconeer.exptool.a121.algo._plugins import (
    DetectorBackendPluginBase,
    DetectorPlotPluginBase,
    DetectorViewPluginBase,
)
from acconeer.exptool.app.new import (
    BUTTON_ICON_COLOR,
    AppModel,
    AttrsConfigEditor,
    BackendLogger,
    GeneralMessage,
    GridGroupBox,
    Message,
    MiscErrorView,
    PidgetFactoryMapping,
    PluginFamily,
    PluginGeneration,
    PluginPresetBase,
    PluginSpecBase,
    PluginState,
    VerticalGroupBox,
    is_task,
    pidgets,
)
from acconeer.exptool.app.new.ui.plugin_components.range_help_view import RangeHelpView

from ._example_app import ExampleApp, ExampleAppConfig, ExampleAppResult, _load_algo_data


@attrs.mutable(kw_only=True)
class SharedState:
    sensor_id: int = attrs.field(default=1)
    config: ExampleAppConfig = attrs.field(factory=ExampleAppConfig)


class PluginPresetId(Enum):
    DEFAULT = auto()


class BackendPlugin(DetectorBackendPluginBase[SharedState]):

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
        self.broadcast(sync=True)

    @is_task
    def update_sensor_id(self, *, sensor_id: int) -> None:
        self.shared_state.sensor_id = sensor_id
        self.broadcast(sync=True)

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
        self.broadcast(sync=True)

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
        self.callback(
            GeneralMessage(
                name="setup",
                kwargs=dict(
                    example_app_config=self.shared_state.config,
                ),
                recipient="plot_plugin",
            )
        )

    def end_session(self) -> None:
        if self._example_app_instance is None:
            raise RuntimeError
        self._example_app_instance.stop()

    def get_next(self) -> None:
        assert self.client
        if self._example_app_instance is None:
            raise RuntimeError
        result = self._example_app_instance.get_next()

        self.callback(GeneralMessage(name="plot", data=result, recipient="plot_plugin"))


class PlotPlugin(DetectorPlotPluginBase):

    _VELOCITY_Y_SCALE_MARGIN_M = 0.25

    def __init__(self, *, plot_layout: pg.GraphicsLayout, app_model: AppModel) -> None:
        super().__init__(plot_layout=plot_layout, app_model=app_model)

    def setup_from_message(self, message: GeneralMessage) -> None:
        assert message.kwargs is not None
        self.setup(**message.kwargs)

    def update_from_message(self, message: GeneralMessage) -> None:
        assert isinstance(message.data, ExampleAppResult)
        self.update(message.data)

    def setup(
        self,
        example_app_config: ExampleAppConfig,
    ) -> None:

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

    def update(self, example_app_result: ExampleAppResult) -> None:
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

        lim = self.psd_smooth_max.update(processor_extra_result.psd)
        self.psd_plot.setYRange(np.log(0.5), np.log(lim))
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

        self.range_helper = RangeHelpView()
        scrolly_layout.addWidget(self.range_helper)

        self.config_editor = AttrsConfigEditor[ExampleAppConfig](
            title="Example app parameters",
            factory_mapping=self._get_pidget_mapping(),
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
                name_label_text="Surface distance",
                suffix=" m",
                decimals=2,
                limits=(0.1, 3),
            ),
            "sensor_angle": pidgets.FloatPidgetFactory(
                name_label_text="Sensor angle",
                suffix=" degrees",
                decimals=1,
                limits=(0, 89),
            ),
            "num_points": pidgets.IntPidgetFactory(
                name_label_text="Number of distance points",
                limits=(1, None),
            ),
            "sweep_rate": pidgets.FloatPidgetFactory(
                name_label_text="Sweep rate",
                suffix=" Hz",
                decimals=1,
                limits=(100, None),
            ),
            "sweeps_per_frame": pidgets.IntPidgetFactory(
                name_label_text="Sweeps per frame",
                limits=(64, 2048),
            ),
            "hwaas": pidgets.IntPidgetFactory(
                name_label_text="HWAAS",
                limits=(1, 511),
            ),
            "profile": pidgets.OptionalEnumPidgetFactory(
                name_label_text="Profile",
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
                limits=(1, None),
            ),
            "frame_rate": pidgets.OptionalFloatPidgetFactory(
                name_label_text="Frame rate",
                checkbox_label_text="Limit",
                suffix=" Hz",
                decimals=1,
                limits=(1, None),
                init_set_value=10,
            ),
            "continuous_sweep_mode": pidgets.CheckboxPidgetFactory(
                name_label_text="Continuos sweep mode",
            ),
            "double_buffering": pidgets.CheckboxPidgetFactory(
                name_label_text="Double buffering",
            ),
            "inter_frame_idle_state": pidgets.EnumPidgetFactory(
                enum_type=a121.IdleState,
                name_label_text="Inter frame idle state",
                label_mapping={
                    a121.IdleState.DEEP_SLEEP: "Deep sleep",
                    a121.IdleState.SLEEP: "Sleep",
                    a121.IdleState.READY: "Ready",
                },
            ),
            "inter_sweep_idle_state": pidgets.EnumPidgetFactory(
                enum_type=a121.IdleState,
                name_label_text="Inter sweep idle state",
                label_mapping={
                    a121.IdleState.DEEP_SLEEP: "Deep sleep",
                    a121.IdleState.SLEEP: "Sleep",
                    a121.IdleState.READY: "Ready",
                },
            ),
            "time_series_length": pidgets.IntPidgetFactory(
                name_label_text="Time series length",
                limits=(64, None),
            ),
            "psd_lp_coeff": pidgets.FloatSliderPidgetFactory(
                name_label_text="PSD time filtering coeff.",
                limits=(0, 1),
                decimals=3,
            ),
            "slow_zone": pidgets.IntPidgetFactory(
                name_label_text="Slow zone half length",
                limits=(0, 20),
            ),
            "velocity_lp_coeff": pidgets.FloatSliderPidgetFactory(
                name_label_text="Velocity time filtering coeff.\nper time series",
                limits=(0, 1),
                decimals=3,
            ),
            "cfar_win": pidgets.IntPidgetFactory(
                name_label_text="CFAR window length",
                limits=(0, 20),
            ),
            "cfar_guard": pidgets.IntPidgetFactory(
                name_label_text="CFAR guard length",
                limits=(0, 20),
            ),
            "cfar_sensitivity": pidgets.FloatSliderPidgetFactory(
                name_label_text="Threshold sensitivity",
                decimals=2,
                limits=(0.01, 1),
            ),
            "max_peak_interval_s": pidgets.FloatPidgetFactory(
                name_label_text="Max peak interval",
                decimals=1,
                limits=(0, 20),
                suffix=" s",
            ),
        }

    def on_backend_state_update(self, backend_plugin_state: Optional[SharedState]) -> None:
        if backend_plugin_state is not None and backend_plugin_state.config is not None:
            results = backend_plugin_state.config._collect_validation_results()

            not_handled = self.config_editor.handle_validation_results(results)

            not_handled = self.misc_error_view.handle_validation_results(not_handled)

            assert not_handled == []

            self.range_helper.update(
                ExampleApp._get_sensor_config(backend_plugin_state.config).subsweep
            )

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
        self.sensor_id_pidget.set_selected_sensor(state.sensor_id, app_model.connected_sensors)
        self.sensor_id_pidget.setEnabled(app_model.plugin_state.is_steady)

        self.start_button.setEnabled(
            app_model.is_ready_for_session() and self.config_editor.is_ready
        )
        self.stop_button.setEnabled(app_model.plugin_state == PluginState.LOADED_BUSY)

    def _on_config_update(self, config: ExampleAppConfig) -> None:
        self.app_model.put_backend_plugin_task("update_config", {"config": config})

    def handle_message(self, message: GeneralMessage) -> None:
        if message.name == "sync":
            self._log.debug(f"{type(self).__name__} syncing")

            self.config_editor.sync()
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


SURFACE_VELOCITY_PLUGIN = PluginSpec(
    generation=PluginGeneration.A121,
    key="surface_velocity",
    title="Surface velocity",
    description="Estimate surface speed and direction of streaming water.",
    family=PluginFamily.EXAMPLE_APP,
    presets=[
        PluginPresetBase(name="Default", preset_id=PluginPresetId.DEFAULT),
    ],
    default_preset_id=PluginPresetId.DEFAULT,
)
