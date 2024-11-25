# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved

from __future__ import annotations

import logging
import time
from enum import Enum, auto
from typing import Callable, Mapping, Optional

import attrs
import h5py

from PySide6.QtWidgets import QPushButton, QVBoxLayout

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121, opser
from acconeer.exptool._core.docstrings import get_attribute_docstring
from acconeer.exptool.a121.algo._plugins import (
    A121BackendPluginBase,
    A121ViewPluginBase,
)
from acconeer.exptool.a121.algo.presence import DetectorConfig
from acconeer.exptool.a121.algo.presence._pidget_mapping import (
    get_pidget_mapping as _get_presence_pidget_mapping,
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
from acconeer.exptool.app.new.ui.components import CollapsibleWidget

from ._example_app import ExampleAppConfig
from ._mode_handler import (
    AppMode,
    DetectionState,
    ModeHandler,
    ModeHandlerConfig,
    ModeHandlerResult,
    _load_algo_data,
    get_default_config,
)


opser.register_json_presentable(ModeHandlerConfig)


log = logging.getLogger(__name__)


@attrs.mutable(kw_only=True)
class SharedState:
    sensor_id: int = attrs.field(default=1)
    config: ModeHandlerConfig = attrs.field(factory=ModeHandlerConfig)


class PluginPresetId(Enum):
    DEFAULT = auto()


@attrs.frozen(kw_only=True)
class SetupMessage(GeneralMessage):
    mode_handler_config: ModeHandlerConfig
    name: str = attrs.field(default="setup", init=False)
    recipient: backend.RecipientLiteral = attrs.field(default="plot_plugin", init=False)


class BackendPlugin(A121BackendPluginBase[SharedState]):
    PLUGIN_PRESETS: Mapping[int, Callable[[], ModeHandlerConfig]] = {
        PluginPresetId.DEFAULT.value: lambda: get_default_config()
    }

    def __init__(
        self, callback: Callable[[Message], None], generation: PluginGeneration, key: str
    ) -> None:
        super().__init__(callback=callback, generation=generation, key=key)

        self._recorder: Optional[a121.H5Recorder] = None
        self._exempel_app_instance: Optional[ModeHandler] = None
        self._log = BackendLogger.getLogger(__name__)

        self.restore_defaults()

    def _load_from_cache(self, file: h5py.File) -> None:
        self.shared_state.config = opser.deserialize(file["config"], ModeHandlerConfig)

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
    def update_config(self, *, config: ModeHandlerConfig) -> None:
        self.shared_state.config = config
        self.broadcast()

    def save_to_cache(self, file: h5py.File) -> None:
        cfg_group = file.create_group("config")
        opser.serialize(self.shared_state.config, cfg_group)

    @is_task
    def set_preset(self, preset_id: int) -> None:
        preset_config = self.PLUGIN_PRESETS[preset_id]
        self.shared_state.config = preset_config()
        self.broadcast()

    def load_from_record_setup(self, *, record: a121.H5Record) -> None:
        algo_group = record.get_algo_group(self.key)
        _, config = _load_algo_data(algo_group)
        self.shared_state.config = config
        self.shared_state.sensor_id = record.session(0).sensor_id

    def _start_session(self, recorder: Optional[a121.H5Recorder]) -> None:
        assert self.client
        self._example_app_instance = ModeHandler(
            client=self.client,
            sensor_id=self.shared_state.sensor_id,
            mode_handler_config=self.shared_state.config,
        )
        self._example_app_instance.start(recorder)
        self.callback(SetupMessage(mode_handler_config=self.shared_state.config))

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
    def __init__(self, app_model: AppModel) -> None:
        super().__init__(app_model=app_model)
        self._plot_job: Optional[ModeHandlerResult] = None
        self._is_setup = False

    def handle_message(self, message: backend.GeneralMessage) -> None:
        if isinstance(message, backend.PlotMessage):
            if not isinstance(message.result, ModeHandlerResult):
                msg = f"Unexpected result type: {type(message.result)}"
                raise RuntimeError(msg)

            self._plot_job = message.result
        elif isinstance(message, SetupMessage):
            self.setup(mode_handler_config=message.mode_handler_config)
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
        mode_handler_config: ModeHandlerConfig,
    ) -> None:
        self.plot_layout.clear()

        brush = et.utils.pg_brush_cycler(0)
        symbol_dot_kw = dict(symbol="o", symbolSize=10, symbolBrush=brush, symbolPen="k")

        self.history_plot = self.plot_layout.addPlot()
        self.history_plot.setMenuEnabled(False)
        self.history_plot.showGrid(x=False, y=True)
        self.history_plot.setLabel("left", "Score")
        self.history_plot.setLabel("bottom", "Time (s)")

        self.history_curve = self.history_plot.plot(
            **dict(pen=et.utils.pg_pen_cycler(0), **symbol_dot_kw)
        )

        self.threshold_line = pg.InfiniteLine(pen=et.utils.pg_pen_cycler(1), angle=0)
        self.history_plot.addItem(self.threshold_line)
        self.threshold_line.show()

        self.smooth_max_history = et.utils.SmoothMax(tau_decay=10.0)

        self.present_html_format = (
            '<div style="text-align: center">'
            '<span style="color: #FFFFFF;font-size:16pt;">'
            "{}</span></div>"
        )
        self.not_present_html = (
            '<div style="text-align: center">'
            '<span style="color: #FFFFFF;font-size:16pt;">'
            "{}</span></div>"
        )
        self.not_present_text_item = pg.TextItem(
            fill=pg.mkColor(0xFF, 0x7F, 0x0E, 200),
            anchor=(0.5, 0),
        )
        self.present_text_item = pg.TextItem(
            html=self.not_present_html,
            fill=pg.mkColor(0x1F, 0x77, 0xB4, 180),
            anchor=(0.5, 0),
        )
        self.present_text_item.hide()
        self.not_present_text_item.hide()
        self.history_plot.addItem(self.present_text_item)
        self.history_plot.addItem(self.not_present_text_item)

        self.history_plot.setXRange(-10, 0)
        self.history_plot.setYRange(0, 5)

    def draw_plot_job(self, example_app_result: ModeHandlerResult) -> None:
        if example_app_result.app_mode == AppMode.PRESENCE:
            self.history_plot.setXRange(-10, 0)
            self.history_plot.setYRange(0, 5)
            self.history_curve.setData([], [])
            num_dots = int(time.time() * 2 % 3) + 1
            present_html = self.not_present_html.format("Monitoring presence" + "." * num_dots)
            self.not_present_text_item.setHtml(present_html)
            self.not_present_text_item.show()
        elif (
            example_app_result.app_mode == AppMode.HANDMOTION
            and example_app_result.example_app_result is not None
        ):
            history = example_app_result.example_app_result.extra_result.history
            history_time = example_app_result.example_app_result.extra_result.history_time
            threshold = example_app_result.example_app_result.extra_result.threshold
            detection_state = example_app_result.detection_state

            lim = max(self.smooth_max_history.update(history), threshold + 1)
            self.history_curve.setData(history_time, history)
            self.history_plot.setYRange(0, lim)
            self.threshold_line.setValue(threshold)

            if detection_state is DetectionState.NO_DETECTION:
                present_html = self.not_present_html.format("No hand detected")
                self.not_present_text_item.setHtml(present_html)
                self.not_present_text_item.show()
                self.present_text_item.hide()
            else:
                if detection_state is DetectionState.DETECTION:
                    present_html = self.present_html_format.format("Hand detected")
                elif detection_state is DetectionState.RETENTION:
                    present_html = self.present_html_format.format("Retaining detection")
                self.present_text_item.setHtml(present_html)
                self.present_text_item.show()
                self.not_present_text_item.hide()

        text_y_pos = self.history_plot.getAxis("left").range[1] * 0.95
        text_x_pos = (
            self.history_plot.getAxis("bottom").range[1]
            + self.history_plot.getAxis("bottom").range[0]
        ) / 2.0

        self.not_present_text_item.setPos(text_x_pos, text_y_pos)
        self.present_text_item.setPos(text_x_pos, text_y_pos)


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
            title="Mode handler parameters",
            factory_mapping=self._get_example_app_pidget_mapping(),
            config_type=ModeHandlerConfig,
            parent=self.scrolly_widget,
        )
        self.config_editor.sig_update.connect(self._on_config_update)
        scrolly_layout.addWidget(self.config_editor)

        self.setup_editor = AttrsConfigEditor(
            title="Hand motion - Setup parameters",
            factory_mapping=self._get_setup_pidget_mapping(),
            config_type=ExampleAppConfig,
            parent=self.scrolly_widget,
        )
        self.setup_editor.sig_update.connect(self._on_example_app_config_update)
        scrolly_layout.addWidget(self.setup_editor)

        self.filtering_editor = AttrsConfigEditor(
            title="Hand motion - Filtering parameters",
            factory_mapping=self._get_filtering_pidget_mapping(),
            config_type=ExampleAppConfig,
            parent=self.scrolly_widget,
        )
        self.filtering_editor.sig_update.connect(self._on_example_app_config_update)
        scrolly_layout.addWidget(self.filtering_editor)

        self.sensor_config_editor = AttrsConfigEditor(
            title="Hand motion - Sensor configuration parameters",
            factory_mapping=self._get_sensor_config_pidget_mapping(),
            config_type=ExampleAppConfig,
            parent=self.scrolly_widget,
        )
        self.sensor_config_editor.sig_update.connect(self._on_example_app_config_update)
        scrolly_layout.addWidget(self.sensor_config_editor)

        self.presence_config_editor = AttrsConfigEditor(
            title="Presence - Detector parameters",
            factory_mapping=_get_presence_pidget_mapping(),
            config_type=DetectorConfig,
            parent=self.scrolly_widget,
        )
        self.presence_config_editor.sig_update.connect(self._on_presence_config_update)
        self.collapsible_widget = CollapsibleWidget(
            "Presence configuration parameters", self.presence_config_editor, self.scrolly_widget
        )
        scrolly_layout.addWidget(self.collapsible_widget)

        self.sticky_widget.setLayout(sticky_layout)
        self.scrolly_widget.setLayout(scrolly_layout)

    @classmethod
    def _get_example_app_pidget_mapping(cls) -> PidgetFactoryMapping:
        return {
            "hand_detection_timeout": pidgets.FloatPidgetFactory(
                name_label_text="Hand motion timeout limit:",
                name_label_tooltip=get_attribute_docstring(
                    ModeHandlerConfig, "hand_detection_timeout"
                ),
                limits=(0, None),
                decimals=1,
                suffix="s",
            ),
            "use_presence_detection": pidgets.CheckboxPidgetFactory(
                name_label_text="Enable low-power mode",
                name_label_tooltip=get_attribute_docstring(
                    ModeHandlerConfig, "use_presence_detection"
                ),
            ),
        }

    @classmethod
    def _get_setup_pidget_mapping(cls) -> PidgetFactoryMapping:
        return {
            "sensor_to_water_distance": pidgets.FloatPidgetFactory(
                name_label_text="Distance between sensor and water jet:",
                name_label_tooltip=get_attribute_docstring(
                    ExampleAppConfig, "sensor_to_water_distance"
                ),
                limits=(0, 0.3),
                decimals=3,
                suffix="m",
            ),
            "water_jet_width": pidgets.FloatPidgetFactory(
                name_label_text="Water jet width:",
                name_label_tooltip=get_attribute_docstring(ExampleAppConfig, "water_jet_width"),
                limits=(0, 0.1),
                decimals=3,
                suffix="m",
            ),
            "measurement_range_end": pidgets.FloatPidgetFactory(
                name_label_text="Measurement range end:",
                name_label_tooltip=get_attribute_docstring(
                    ExampleAppConfig, "measurement_range_end"
                ),
                limits=(0, 0.5),
                decimals=3,
                suffix="m",
            ),
        }

    @classmethod
    def _get_filtering_pidget_mapping(cls) -> PidgetFactoryMapping:
        return {
            "threshold": pidgets.FloatSliderPidgetFactory(
                name_label_text="Threshold:",
                name_label_tooltip=get_attribute_docstring(ExampleAppConfig, "threshold"),
                limits=(0, 5),
                decimals=2,
            ),
            "filter_time_const": pidgets.FloatSliderPidgetFactory(
                name_label_text="Filter constant:",
                name_label_tooltip=get_attribute_docstring(ExampleAppConfig, "filter_time_const"),
                limits=(0, 2.0),
                decimals=2,
                suffix="s",
            ),
            "detection_retention_duration": pidgets.FloatSliderPidgetFactory(
                name_label_text="Detection retention duration:",
                name_label_tooltip=get_attribute_docstring(
                    ExampleAppConfig, "detection_retention_duration"
                ),
                limits=(0, 5),
                decimals=1,
                suffix="s",
            ),
        }

    @classmethod
    def _get_sensor_config_pidget_mapping(cls) -> PidgetFactoryMapping:
        return {
            "sweeps_per_frame": pidgets.IntPidgetFactory(
                name_label_text="Sweeps per frame:",
                name_label_tooltip=get_attribute_docstring(ExampleAppConfig, "sweeps_per_frame"),
                limits=(1, 1000),
            ),
            "sweeps_rate": pidgets.IntPidgetFactory(
                name_label_text="Sweep rate:",
                name_label_tooltip=get_attribute_docstring(ExampleAppConfig, "sweeps_rate"),
                limits=(1, 5000),
                suffix="Hz",
            ),
            "frame_rate": pidgets.IntPidgetFactory(
                name_label_text="Frame rate:",
                name_label_tooltip=get_attribute_docstring(ExampleAppConfig, "frame_rate"),
                limits=(1, 100),
                suffix="Hz",
            ),
            "hwaas": pidgets.IntPidgetFactory(
                name_label_text="HWAAS:",
                name_label_tooltip=get_attribute_docstring(ExampleAppConfig, "hwaas"),
                limits=(1, 511),
            ),
        }

    def on_backend_state_update(self, state: Optional[SharedState]) -> None:
        if state is None:
            self.sensor_config_editor.set_data(None)
            self.config_editor.set_data(None)
            self.filtering_editor.set_data(None)
            self.setup_editor.set_data(None)
            self.presence_config_editor.set_data(None)
        else:
            self.sensor_id_pidget.set_data(state.sensor_id)
            self.config_editor.set_data(state.config)
            self.filtering_editor.set_data(state.config.example_app_config)
            self.setup_editor.set_data(state.config.example_app_config)
            self.sensor_config_editor.set_data(state.config.example_app_config)
            self.presence_config_editor.set_data(state.config.presence_config)

            results = state.config._collect_validation_results()

            not_handled = self.filtering_editor.handle_validation_results(results)

            not_handled = self.misc_error_view.handle_validation_results(not_handled)

            assert not_handled == []

    def on_app_model_update(self, app_model: AppModel) -> None:
        self.sensor_id_pidget.set_selectable_sensors(app_model.connected_sensors)

        visual_policies.apply_enabled_policy(
            visual_policies.config_editor_enabled,
            app_model,
            widgets=[
                self.sensor_id_pidget,
                self.config_editor,
                self.filtering_editor,
                self.setup_editor,
                self.sensor_config_editor,
                self.presence_config_editor,
            ],
        )

        configs_valid = (
            self.filtering_editor.is_ready
            and self.sensor_config_editor.is_ready
            and self.setup_editor.is_ready
        )
        self.start_button.setEnabled(
            visual_policies.start_button_enabled(app_model, extra_condition=configs_valid)
        )
        self.stop_button.setEnabled(visual_policies.stop_button_enabled(app_model))

    def _on_config_update(self, config: ModeHandlerConfig) -> None:
        BackendPlugin.update_config.rpc(self.app_model.put_task, config=config)

    def _on_example_app_config_update(self, example_app_config: ExampleAppConfig) -> None:
        config = self.config_editor.get_data()
        assert config is not None
        config.example_app_config = example_app_config
        BackendPlugin.update_config.rpc(self.app_model.put_task, config=config)

    def _on_presence_config_update(self, detector_config: DetectorConfig) -> None:
        config = self.config_editor.get_data()
        assert config is not None
        config.presence_config = detector_config
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


HAND_MOTION_PLUGIN = PluginSpec(
    generation=PluginGeneration.A121,
    key="hand_motion",
    title="Hand motion detection",
    docs_link="https://docs.acconeer.com/en/latest/example_apps/a121/hand_motion_detection.html",
    description="Wake-up water faucet application.",
    family=PluginFamily.EXAMPLE_APP,
    presets=[
        PluginPresetBase(name="Default", preset_id=PluginPresetId.DEFAULT),
    ],
    default_preset_id=PluginPresetId.DEFAULT,
)
