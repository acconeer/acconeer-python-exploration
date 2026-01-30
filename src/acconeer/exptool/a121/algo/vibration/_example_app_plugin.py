# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved

from __future__ import annotations

import logging
from enum import Enum, auto
from typing import Callable, Mapping, Optional

import attrs
import h5py

from PySide6.QtWidgets import QPushButton, QVBoxLayout

from acconeer.exptool import a121
from acconeer.exptool._core.docstrings import get_attribute_docstring
from acconeer.exptool.a121._h5_utils import _create_h5_string_dataset
from acconeer.exptool.a121.algo._plugins import (
    A121BackendPluginBase,
    A121ViewPluginBase,
)
from acconeer.exptool.a121.algo._utils import APPROX_BASE_STEP_LENGTH_M
from acconeer.exptool.a121.algo.vibration import (
    ReportedDisplacement,
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

from ._configs import get_high_frequency_config, get_low_frequency_config
from ._example_app import ExampleApp, ExampleAppConfig, ExampleAppResult, _load_algo_data
from .plot import VibrationPlot


log = logging.getLogger(__name__)


class PluginPresetId(Enum):
    LOW_FREQ = auto()
    HIGH_FREQ = auto()


@attrs.mutable(kw_only=True)
class SharedState:
    sensor_id: int = attrs.field(default=1)
    config: ExampleAppConfig = attrs.field(factory=ExampleAppConfig)


@attrs.frozen(kw_only=True)
class SetupMessage(GeneralMessage):
    example_app_config: ExampleAppConfig
    name: str = attrs.field(default="setup", init=False)
    recipient: backend.RecipientLiteral = attrs.field(default="plot_plugin", init=False)


class BackendPlugin(A121BackendPluginBase[SharedState]):
    PLUGIN_PRESETS: Mapping[int, Callable[[], ExampleAppConfig]] = {
        PluginPresetId.LOW_FREQ.value: lambda: get_low_frequency_config(),
        PluginPresetId.HIGH_FREQ.value: lambda: get_high_frequency_config(),
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

        self.sensor_config_editor = AttrsConfigEditor(
            title="Sensor parameters",
            factory_mapping=self._get_sensor_pidget_mapping(),
            config_type=ExampleAppConfig,
            parent=self.scrolly_widget,
        )
        self.sensor_config_editor.sig_update.connect(self._on_config_update)
        scrolly_layout.addWidget(self.sensor_config_editor)

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
    def _get_sensor_pidget_mapping(cls) -> PidgetFactoryMapping:
        # Note: Incomplete mapping
        return {
            "measured_point": pidgets.IntPidgetFactory(
                name_label_text="Measured point:",
                name_label_tooltip=get_attribute_docstring(ExampleAppConfig, "measured_point"),
                limits=(0, None),
            ),
            "profile": pidgets.EnumPidgetFactory(
                name_label_text="Profile:",
                name_label_tooltip=get_attribute_docstring(ExampleAppConfig, "profile"),
                enum_type=a121.Profile,
                label_mapping={
                    a121.Profile.PROFILE_1: "1 (shortest)",
                    a121.Profile.PROFILE_2: "2",
                    a121.Profile.PROFILE_3: "3",
                    a121.Profile.PROFILE_4: "4",
                    a121.Profile.PROFILE_5: "5 (longest)",
                },
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
            "sweep_rate": pidgets.FloatPidgetFactory(
                name_label_text="Sweep rate:",
                name_label_tooltip=get_attribute_docstring(ExampleAppConfig, "sweep_rate"),
                suffix=" Hz",
                decimals=1,
                limits=(1, None),
            ),
            "sweeps_per_frame": pidgets.IntPidgetFactory(
                name_label_text="Sweeps per frame:",
                name_label_tooltip=get_attribute_docstring(ExampleAppConfig, "sweeps_per_frame"),
                limits=(1, 2048),
            ),
            "hwaas": pidgets.IntPidgetFactory(
                name_label_text="HWAAS:",
                name_label_tooltip=get_attribute_docstring(ExampleAppConfig, "hwaas"),
                limits=(1, 511),
            ),
            "double_buffering": pidgets.CheckboxPidgetFactory(
                name_label_text="Double buffering",
                name_label_tooltip=get_attribute_docstring(ExampleAppConfig, "double_buffering"),
            ),
            "continuous_sweep_mode": pidgets.CheckboxPidgetFactory(
                name_label_text="Continuos sweep mode",
                name_label_tooltip=get_attribute_docstring(
                    ExampleAppConfig, "continuous_sweep_mode"
                ),
            ),
            "inter_frame_idle_state": pidgets.EnumPidgetFactory(
                enum_type=a121.IdleState,
                name_label_text="Inter frame idle state:",
                name_label_tooltip=get_attribute_docstring(
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
                name_label_tooltip=get_attribute_docstring(
                    ExampleAppConfig, "inter_sweep_idle_state"
                ),
                label_mapping={
                    a121.IdleState.DEEP_SLEEP: "Deep sleep",
                    a121.IdleState.SLEEP: "Sleep",
                    a121.IdleState.READY: "Ready",
                },
            ),
        }

    @classmethod
    def _get_pidget_mapping(cls) -> PidgetFactoryMapping:
        # Note: Incomplete mapping
        return {
            "time_series_length": pidgets.IntPidgetFactory(
                name_label_text="Time series length:",
                name_label_tooltip=get_attribute_docstring(ExampleAppConfig, "time_series_length"),
                limits=(0, None),
            ),
            "lp_coeff": pidgets.FloatSliderPidgetFactory(
                name_label_text="Time filtering coefficient:",
                name_label_tooltip=get_attribute_docstring(ExampleAppConfig, "lp_coeff"),
                suffix="",
                limits=(0, 1),
                decimals=2,
            ),
            "threshold_margin": pidgets.FloatSliderPidgetFactory(
                name_label_text="Threshold margin:",
                name_label_tooltip=get_attribute_docstring(ExampleAppConfig, "threshold_margin"),
                suffix="um",
                limits=(0, 100),
                decimals=1,
            ),
            "amplitude_threshold": pidgets.FloatPidgetFactory(
                name_label_text="Amplitude threshold:",
                name_label_tooltip=get_attribute_docstring(
                    ExampleAppConfig, "amplitude_threshold"
                ),
                decimals=0,
                limits=(0, None),
            ),
            "reported_displacement_mode": pidgets.EnumPidgetFactory(
                name_label_text="Displacement mode:",
                name_label_tooltip=get_attribute_docstring(
                    ExampleAppConfig, "reported_displacement_mode"
                ),
                enum_type=ReportedDisplacement,
                label_mapping={
                    ReportedDisplacement.AMPLITUDE: "Amplitude",
                    ReportedDisplacement.PEAK2PEAK: "Peak to peak",
                },
            ),
            "low_frequency_enhancement": pidgets.CheckboxPidgetFactory(
                name_label_text="Low frequency enhancement",
                name_label_tooltip=get_attribute_docstring(
                    ExampleAppConfig, "low_frequency_enhancement"
                ),
            ),
        }

    def on_backend_state_update(self, state: Optional[SharedState]) -> None:
        if state is None:
            self.config_editor.set_data(None)
            self.sensor_config_editor.set_data(None)
        else:
            self.config_editor.set_data(state.config)
            self.sensor_config_editor.set_data(state.config)
            self.sensor_id_pidget.set_data(state.sensor_id)

            results = state.config._collect_validation_results()

            not_handled = self.config_editor.handle_validation_results(results)

            not_handled = self.misc_error_view.handle_validation_results(not_handled)

            assert not_handled == []

            not_handled = self.sensor_config_editor.handle_validation_results(results)

            not_handled = self.misc_error_view.handle_validation_results(not_handled)

            assert not_handled == []

            self.range_helper.set_data(ExampleApp._get_sensor_config(state.config).subsweeps[0])

    def on_app_model_update(self, app_model: AppModel) -> None:
        self.sensor_id_pidget.set_selectable_sensors(app_model.connected_sensors)

        visual_policies.apply_enabled_policy(
            visual_policies.config_editor_enabled,
            app_model,
            widgets=[self.config_editor, self.sensor_id_pidget],
        )

        visual_policies.apply_enabled_policy(
            visual_policies.config_editor_enabled,
            app_model,
            widgets=[self.sensor_config_editor, self.sensor_id_pidget],
        )

        self.start_button.setEnabled(
            visual_policies.start_button_enabled(
                app_model,
                extra_condition=self.config_editor.is_ready and self.sensor_config_editor.is_ready,
            )
        )
        self.stop_button.setEnabled(visual_policies.stop_button_enabled(app_model))

    def _on_config_update(self, config: ExampleAppConfig) -> None:
        BackendPlugin.update_config.rpc(self.app_model.put_task, config=config)

    def _send_defaults_request(self) -> None:
        BackendPlugin.restore_defaults.rpc(self.app_model.put_task)

    def _on_sensor_id_update(self, sensor_id: int) -> None:
        BackendPlugin.update_sensor_id.rpc(self.app_model.put_task, sensor_id=sensor_id)


class PlotPlugin(PgPlotPlugin):
    def __init__(self, app_model: AppModel) -> None:
        super().__init__(app_model=app_model)
        self._plot_job: Optional[ExampleAppResult] = None
        self._is_setup = False
        self._vibration_plot = VibrationPlot()

    def handle_message(self, message: backend.GeneralMessage) -> None:
        if isinstance(message, backend.PlotMessage):
            self._plot_job = message.result
        elif isinstance(message, SetupMessage):
            self._setup(example_app_config=message.example_app_config)
            self._is_setup = True
        else:
            log.warn(f"{self.__class__.__name__} got an unsupported command: {message.name!r}.")

    def draw(self) -> None:
        if not self._is_setup or self._plot_job is None:
            return

        try:
            self._draw_plot_job(example_app_result=self._plot_job)
        finally:
            self._plot_job = None

    def _setup(self, example_app_config: ExampleAppConfig) -> None:
        self.plot_layout.clear()
        meas_dist_m = example_app_config.measured_point * APPROX_BASE_STEP_LENGTH_M
        self._vibration_plot.setup_plot(self.plot_layout, meas_dist_m)

    def _draw_plot_job(self, example_app_result: ExampleAppResult) -> None:
        self._vibration_plot.update_plot(
            result=example_app_result,
            extra_result=example_app_result.processor_extra_result,
        )


class PluginSpec(PluginSpecBase):
    def create_backend_plugin(
        self, callback: Callable[[Message], None], key: str
    ) -> BackendPlugin:
        return BackendPlugin(callback=callback, generation=self.generation, key=key)

    def create_view_plugin(self, app_model: AppModel) -> ViewPlugin:
        return ViewPlugin(app_model=app_model)

    def create_plot_plugin(self, app_model: AppModel) -> PlotPlugin:
        return PlotPlugin(app_model=app_model)


VIBRATION_PLUGIN = PluginSpec(
    generation=PluginGeneration.A121,
    key="vibration",
    title="Vibration measurement",
    docs_link="https://docs.acconeer.com/en/latest/example_apps/a121/vibration.html",
    description="Quantify the frequency content of vibrating object.",
    family=PluginFamily.EXAMPLE_APP,
    presets=[
        PluginPresetBase(name="Low frequency", preset_id=PluginPresetId.LOW_FREQ),
        PluginPresetBase(name="High frequency", preset_id=PluginPresetId.HIGH_FREQ),
    ],
    default_preset_id=PluginPresetId.LOW_FREQ,
)
