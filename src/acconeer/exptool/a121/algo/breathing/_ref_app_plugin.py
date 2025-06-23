# Copyright (c) Acconeer AB, 2023-2025
# All rights reserved

from __future__ import annotations

import logging
from enum import Enum, auto
from typing import Callable, Mapping, Optional

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
from acconeer.exptool.a121.algo import APPROX_BASE_STEP_LENGTH_M
from acconeer.exptool.a121.algo._plugins import (
    A121BackendPluginBase,
    A121ViewPluginBase,
)
from acconeer.exptool.a121.algo.breathing import (
    AppState,
    BreathingProcessorConfig,
    get_infant_config,
    get_sitting_config,
)
from acconeer.exptool.a121.algo.presence import ProcessorConfig as PresenceProcessorConfig
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

from ._ref_app import (
    RefApp,
    RefAppConfig,
    RefAppResult,
    _load_algo_data,
    get_sensor_config,
)


log = logging.getLogger(__name__)


@attrs.mutable(kw_only=True)
class SharedState:
    sensor_id: int = attrs.field(default=1)
    config: RefAppConfig = attrs.field(factory=RefAppConfig)


class PluginPresetId(Enum):
    SITTING = auto()
    INFANT = auto()


@attrs.frozen(kw_only=True)
class SetupMessage(GeneralMessage):
    ref_app_config: RefAppConfig
    sensor_config: a121.SensorConfig
    name: str = attrs.field(default="setup", init=False)
    recipient: backend.RecipientLiteral = attrs.field(default="plot_plugin", init=False)


class BackendPlugin(A121BackendPluginBase[SharedState]):
    PLUGIN_PRESETS: Mapping[int, Callable[[], RefAppConfig]] = {
        PluginPresetId.SITTING.value: lambda: get_sitting_config(),
        PluginPresetId.INFANT.value: lambda: get_infant_config(),
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
        self._ref_app_instance = RefApp(
            client=self.client,
            sensor_id=self.shared_state.sensor_id,
            ref_app_config=self.shared_state.config,
        )
        self._ref_app_instance.start(recorder)
        self.callback(
            SetupMessage(
                ref_app_config=self.shared_state.config,
                sensor_config=get_sensor_config(self.shared_state.config),
            )
        )

    def end_session(self) -> None:
        if self._ref_app_instance is None:
            raise RuntimeError
        self._ref_app_instance.stop()

    def get_next(self) -> None:
        assert self.client
        if self._ref_app_instance is None:
            raise RuntimeError
        result = self._ref_app_instance.get_next()

        self.callback(backend.PlotMessage(result=result))


class PlotPlugin(PgPlotPlugin):
    displayed_breathing_rate: Optional[str]

    def __init__(self, app_model: AppModel) -> None:
        super().__init__(app_model=app_model)
        self.displayed_breathing_rate = None
        self._plot_job: Optional[RefAppResult] = None
        self._is_setup = False

    def handle_message(self, message: backend.GeneralMessage) -> None:
        if isinstance(message, backend.PlotMessage):
            self._plot_job = message.result
        elif isinstance(message, SetupMessage):
            self.setup(
                message.ref_app_config,
                message.sensor_config,
            )
            self._is_setup = True
        else:
            log.warn(f"{self.__class__.__name__} got an unsupported command: {message.name!r}.")

    def draw(self) -> None:
        if not self._is_setup or self._plot_job is None:
            return

        try:
            self.draw_plot_job(ref_app_result=self._plot_job)
        finally:
            self._plot_job = None

    def setup(
        self,
        ref_app_config: RefAppConfig,
        sensor_config: a121.SensorConfig,
    ) -> None:
        self.plot_layout.clear()

        self.distances = (
            sensor_config.start_point
            + np.arange(sensor_config.num_points) * sensor_config.step_length
        ) * APPROX_BASE_STEP_LENGTH_M
        self.use_presence_processor = ref_app_config.use_presence_processor

        win = self.plot_layout

        # Define pens and font.
        blue_color = et.utils.color_cycler(0)
        orange_color = et.utils.color_cycler(1)
        brush = et.utils.pg_brush_cycler(0)
        self.blue = dict(
            pen=pg.mkPen(blue_color, width=2),
            symbol="o",
            symbolSize=1,
            symbolBrush=brush,
            symbolPen="k",
        )
        self.orange = dict(
            pen=pg.mkPen(orange_color, width=2),
            symbol="o",
            symbolSize=1,
            symbolBrush=brush,
            symbolPen="k",
        )
        self.blue_transparent_pen = pg.mkPen(f"{blue_color}50", width=2)
        self.orange_transparent_pen = pg.mkPen(f"{orange_color}50", width=2)

        brush_dot = et.utils.pg_brush_cycler(1)
        symbol_dot_kw = dict(symbol="o", symbolSize=10, symbolBrush=brush_dot, symbolPen="k")

        font = QFont()
        font.setPixelSize(16)

        # Presence plot.
        self.presence_plot = win.addPlot(row=0, col=0)
        self.presence_plot.setMenuEnabled(False)
        self.presence_plot.showGrid(x=True, y=True)
        self.presence_plot.addLegend()
        self.presence_plot.setLabel("left", "Presence score")
        self.presence_plot.setLabel("bottom", "Distance (m)")
        self.presence_plot.addItem(pg.PlotDataItem())
        self.presence_plot_curve = []
        self.presence_plot_curve.append(self.presence_plot.plot(**self.blue))
        self.presence_plot_curve.append(self.presence_plot.plot(**self.orange))
        self.presence_plot_curve.append(self.presence_plot.plot(**self.blue))
        self.presence_plot_curve.append(self.presence_plot.plot(**self.orange))

        self.presence_plot_legend = pg.LegendItem(offset=(0.0, 0.5))
        self.presence_plot_legend.setParentItem(self.presence_plot)
        self.presence_plot_legend.addItem(self.presence_plot_curve[2], "Slow motion")
        self.presence_plot_legend.addItem(self.presence_plot_curve[3], "Fast motion")
        self.presence_plot_legend.show()

        self.presence_smoot_max = et.utils.SmoothMax()

        self.presence_text_item = pg.TextItem(
            fill=pg.mkColor(0xFF, 0x7F, 0x0E, 200),
            anchor=(0.5, 0),
            color=pg.mkColor(0xFF, 0xFF, 0xFF, 200),
        )
        self.presence_text_item.setFont(font)
        self.presence_text_item.show()
        self.presence_plot.addItem(self.presence_text_item)

        # Time series plot.
        self.time_series_plot = win.addPlot(row=1, col=0)
        self.time_series_plot.setMenuEnabled(False)
        self.time_series_plot.showGrid(x=True, y=True)
        self.time_series_plot.addLegend()
        self.time_series_plot.setLabel("left", "Displacement")
        self.time_series_plot.setLabel("bottom", "Time (s)")
        self.time_series_plot.addItem(pg.PlotDataItem())
        self.time_series_curve = self.time_series_plot.plot(**self.blue)

        self.time_series_text_item = pg.TextItem(
            fill=pg.mkColor(0xFF, 0x7F, 0x0E, 200),
            anchor=(0.5, 0),
            color=pg.mkColor(0xFF, 0xFF, 0xFF, 200),
        )
        self.time_series_text_item.setFont(font)
        self.time_series_text_item.show()
        self.time_series_plot.addItem(self.time_series_text_item)

        # Breathing psd plot.
        self.breathing_psd_plot = win.addPlot(row=2, col=0)
        self.breathing_psd_plot.setMenuEnabled(False)
        self.breathing_psd_plot.showGrid(x=True, y=True)
        self.breathing_psd_plot.addLegend()
        self.breathing_psd_plot.setLabel("left", "PSD")
        self.breathing_psd_plot.setLabel("bottom", "Breathing rate (Hz)")
        self.breathing_psd_plot.addItem(pg.PlotDataItem())
        self.breathing_psd_curve = self.breathing_psd_plot.plot(**self.blue)

        self.psd_smoothing = et.utils.SmoothMax()

        # Breathing rate plot.
        self.breathing_rate_plot = win.addPlot(row=3, col=0)
        self.breathing_rate_plot.setMenuEnabled(False)
        self.breathing_rate_plot.showGrid(x=True, y=True)
        self.breathing_rate_plot.addLegend()
        self.breathing_rate_plot.setLabel("left", "Breaths per minute")
        self.breathing_rate_plot.setLabel("bottom", "Time (s)")
        self.breathing_rate_plot.addItem(pg.PlotDataItem())
        self.breathing_rate_curves = []
        self.breathing_rate_curves.append(self.breathing_rate_plot.plot(**self.blue))
        self.breathing_rate_curves.append(
            self.breathing_rate_plot.plot(**dict(pen=None, **symbol_dot_kw))
        )
        self.smooth_breathing_rate = et.utils.SmoothLimits()

        self.breathing_rate_plot_legend = pg.LegendItem(offset=(0.0, 0.5))
        self.breathing_rate_plot_legend.setParentItem(self.breathing_rate_plot)
        self.breathing_rate_plot_legend.addItem(self.breathing_rate_curves[0], "Breathing rate")
        self.breathing_rate_plot_legend.addItem(
            self.breathing_rate_curves[1], "Breathing rate(embedded output)"
        )
        self.breathing_rate_plot_legend.hide()

        self.breathing_rate_text_item = pg.TextItem(
            fill=pg.mkColor(0xFF, 0x7F, 0x0E, 200),
            anchor=(0.5, 0),
            color=pg.mkColor(0xFF, 0xFF, 0xFF, 200),
        )
        self.breathing_rate_text_item.setFont(font)
        self.breathing_rate_text_item.hide()
        self.breathing_rate_plot.addItem(self.breathing_rate_text_item)

    def draw_plot_job(self, *, ref_app_result: RefAppResult) -> None:
        app_state = ref_app_result.app_state

        max_ampl = max(
            np.max(ref_app_result.presence_result.inter),
            np.max(ref_app_result.presence_result.intra),
        )
        lim = self.presence_smoot_max.update(max_ampl)
        self.presence_plot.setYRange(0, lim)

        if ref_app_result.distances_being_analyzed is None:
            self.presence_plot_curve[0].setData(
                self.distances, ref_app_result.presence_result.inter, **self.blue
            )
            self.presence_plot_curve[1].setData(
                self.distances, ref_app_result.presence_result.intra, **self.orange
            )
            self.presence_plot_curve[2].setData([], [])
            self.presence_plot_curve[3].setData([], [])
        else:
            start = ref_app_result.distances_being_analyzed[0]
            end = ref_app_result.distances_being_analyzed[1]
            s = slice(start, end)
            distance_slice = self.distances[s]
            self.presence_plot_curve[0].setData(
                self.distances,
                ref_app_result.presence_result.inter,
                pen=self.blue_transparent_pen,
            )
            self.presence_plot_curve[1].setData(
                self.distances,
                ref_app_result.presence_result.intra,
                pen=self.orange_transparent_pen,
            )
            self.presence_plot_curve[2].setData(
                distance_slice, ref_app_result.presence_result.inter[s]
            )
            self.presence_plot_curve[3].setData(
                distance_slice, ref_app_result.presence_result.intra[s]
            )

        if ref_app_result.breathing_result is not None:
            breathing_result = ref_app_result.breathing_result.extra_result
            breathing_motion = breathing_result.breathing_motion
            psd = breathing_result.psd
            frequencies = breathing_result.frequencies
            time_vector = breathing_result.time_vector
            all_breathing_rate_history = breathing_result.all_breathing_rate_history
            breathing_rate_history = breathing_result.breathing_rate_history

            self.time_series_curve.setData(
                time_vector[-breathing_motion.shape[0] :], breathing_motion
            )
            y = np.max(np.abs(breathing_motion)) * 1.05
            self.time_series_plot.setYRange(-y, y)
            self.time_series_plot.setXRange(
                time_vector[-breathing_motion.shape[0]], max(time_vector)
            )

            if not np.all(np.isnan(all_breathing_rate_history)):
                ylim = self.psd_smoothing.update(psd)
                self.breathing_psd_curve.setData(frequencies, psd)
                self.breathing_psd_plot.setYRange(0, ylim)
                self.breathing_psd_plot.setXRange(0, 2)

                self.breathing_rate_curves[0].setData(time_vector, all_breathing_rate_history)
                lims = self.smooth_breathing_rate.update(all_breathing_rate_history)
                self.breathing_rate_plot.setYRange(lims[0] - 3, lims[1] + 3)

                self.breathing_rate_plot_legend.show()

            if not np.all(np.isnan(breathing_rate_history)):
                self.breathing_rate_curves[1].setData(time_vector, breathing_rate_history)

            if not np.isnan(breathing_rate_history[-1]):
                self.displayed_breathing_rate = "{:.1f}".format(breathing_rate_history[-1])
                self.breathing_rate_text_item.show()

        else:
            self.time_series_plot.setYRange(0, 1)
            self.time_series_plot.setXRange(0, 1)
            self.time_series_curve.setData([], [])
            self.breathing_psd_curve.setData([], [])
            self.breathing_rate_curves[0].setData([], [])
            self.breathing_rate_curves[1].setData([], [])
            self.displayed_breathing_rate = None
            self.breathing_rate_text_item.hide()

        # Set text in text boxes according to app state.

        # Presence text
        if app_state == AppState.NO_PRESENCE_DETECTED:
            presence_text = "No presence detected"
        elif app_state == AppState.DETERMINE_DISTANCE_ESTIMATE:
            presence_text = "Determining distance with presence"
        elif app_state == AppState.ESTIMATE_BREATHING_RATE:
            start_m = "{:.2f}".format(distance_slice[0])
            end_m = "{:.2f}".format(distance_slice[-1])
            if self.use_presence_processor:
                presence_text = (
                    "Presence detected in the range " + start_m + " - " + end_m + " (m)"
                )
            else:
                presence_text = "Presence distance detection disabled"
        elif app_state == AppState.INTRA_PRESENCE_DETECTED:
            presence_text = "Large motion detected"
        else:
            presence_text = ""

        text_y_pos = self.presence_plot.getAxis("left").range[1] * 0.95
        text_x_pos = (
            self.presence_plot.getAxis("bottom").range[1]
            + self.presence_plot.getAxis("bottom").range[0]
        ) / 2.0
        self.presence_text_item.setPos(text_x_pos, text_y_pos)
        self.presence_text_item.setHtml(presence_text)

        # Breathing text
        if app_state == AppState.ESTIMATE_BREATHING_RATE:
            if (
                ref_app_result.breathing_result is not None
                and ref_app_result.breathing_result.breathing_rate is None
            ):
                time_series_text = "Initializing breathing detection"
            elif self.displayed_breathing_rate is not None:
                time_series_text = "Breathing rate: " + self.displayed_breathing_rate + " bpm"
            else:
                time_series_text = ""
        else:
            time_series_text = "Waiting for distance"

        text_y_pos = self.time_series_plot.getAxis("left").range[1] * 0.95
        text_x_pos = (
            self.time_series_plot.getAxis("bottom").range[1]
            + self.time_series_plot.getAxis("bottom").range[0]
        ) / 2.0
        self.time_series_text_item.setPos(text_x_pos, text_y_pos)
        self.time_series_text_item.setHtml(time_series_text)

        if self.displayed_breathing_rate is not None:
            text_y_pos = self.breathing_rate_plot.getAxis("left").range[1] * 0.95
            text_x_pos = time_vector[0]

            self.breathing_rate_text_item.setPos(text_x_pos, text_y_pos)
            self.breathing_rate_text_item.setHtml(self.displayed_breathing_rate + " bpm")


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
            config_type=RefAppConfig,
            title="Ref App parameters",
            factory_mapping=self._get_ref_app_pidget_mapping(),
            parent=self.scrolly_widget,
        )
        self.config_editor.sig_update.connect(self._on_config_update)
        scrolly_layout.addWidget(self.config_editor)

        self.breathing_config_editor = AttrsConfigEditor(
            config_type=BreathingProcessorConfig,
            title="Breathing configuration parameters",
            factory_mapping=self._get_breathing_pidget_mapping(),
            parent=self.scrolly_widget,
        )
        self.breathing_config_editor.sig_update.connect(self._on_breathing_config_update)
        scrolly_layout.addWidget(self.breathing_config_editor)

        self.sensor_config_editor = AttrsConfigEditor(
            config_type=RefAppConfig,
            title="Sensor configuration",
            factory_mapping=self._get_sensor_config_pidget_mapping(),
            parent=self.scrolly_widget,
        )
        self.sensor_config_editor.sig_update.connect(self._on_config_update)
        scrolly_layout.addWidget(self.sensor_config_editor)

        self.presence_config_editor = AttrsConfigEditor(
            config_type=PresenceProcessorConfig,
            title="Presence configuration parameters",
            factory_mapping=self._get_presence_config_pidget_mapping(),
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
    def _get_ref_app_pidget_mapping(cls) -> PidgetGroupFactoryMapping:
        return {
            pidgets.FlatPidgetGroup(): {
                "start_m": pidgets.FloatPidgetFactory(
                    name_label_text="Start:",
                    suffix=" m",
                    decimals=1,
                    limits=(0, None),
                    name_label_tooltip=get_attribute_docstring(RefAppConfig, "start_m"),
                ),
                "end_m": pidgets.FloatPidgetFactory(
                    name_label_text="End:",
                    suffix=" m",
                    decimals=1,
                    limits=(0, None),
                    name_label_tooltip=get_attribute_docstring(RefAppConfig, "end_m"),
                ),
                "num_distances_to_analyze": pidgets.IntPidgetFactory(
                    name_label_text="Number of distances to analyze:",
                    limits=(1, 64),
                    name_label_tooltip=get_attribute_docstring(
                        RefAppConfig, "num_distances_to_analyze"
                    ),
                ),
                "distance_determination_duration": pidgets.FloatPidgetFactory(
                    name_label_text="Duration to determine distance:",
                    suffix=" s",
                    decimals=1,
                    limits=(1, None),
                    name_label_tooltip=get_attribute_docstring(
                        RefAppConfig, "distance_determination_duration"
                    ),
                ),
                "use_presence_processor": pidgets.CheckboxPidgetFactory(
                    name_label_text="Use presence processor to determine distance",
                    name_label_tooltip=get_attribute_docstring(
                        RefAppConfig, "use_presence_processor"
                    ),
                ),
            }
        }

    @classmethod
    def _get_sensor_config_pidget_mapping(cls) -> PidgetGroupFactoryMapping:
        return {
            pidgets.FlatPidgetGroup(): {
                "frame_rate": pidgets.FloatPidgetFactory(
                    name_label_text="Frame rate:",
                    suffix=" Hz",
                    decimals=1,
                    name_label_tooltip=get_attribute_docstring(RefAppConfig, "frame_rate"),
                ),
                "sweeps_per_frame": pidgets.IntPidgetFactory(
                    name_label_text="Sweeps per frame:",
                    limits=(1, 64),
                    name_label_tooltip=get_attribute_docstring(RefAppConfig, "sweeps_per_frame"),
                ),
                "hwaas": pidgets.IntPidgetFactory(
                    name_label_text="HWAAS:",
                    limits=(1, 511),
                    name_label_tooltip=get_attribute_docstring(RefAppConfig, "hwaas"),
                ),
                "profile": pidgets.EnumPidgetFactory(
                    name_label_text="Profile:",
                    enum_type=a121.Profile,
                    label_mapping={
                        a121.Profile.PROFILE_1: "1 (shortest)",
                        a121.Profile.PROFILE_2: "2",
                        a121.Profile.PROFILE_3: "3",
                        a121.Profile.PROFILE_4: "4",
                        a121.Profile.PROFILE_5: "5 (longest)",
                    },
                    name_label_tooltip=get_attribute_docstring(RefAppConfig, "profile"),
                ),
            }
        }

    @classmethod
    def _get_breathing_pidget_mapping(cls) -> PidgetGroupFactoryMapping:
        return {
            pidgets.FlatPidgetGroup(): {
                "lowest_breathing_rate": pidgets.FloatPidgetFactory(
                    name_label_text="Lowest anticipated breathing rate:",
                    suffix=" bpm",
                    limits=(2, None),
                    decimals=1,
                    name_label_tooltip=get_attribute_docstring(
                        BreathingProcessorConfig, "lowest_breathing_rate"
                    ),
                ),
                "highest_breathing_rate": pidgets.FloatPidgetFactory(
                    name_label_text="Highest anticipated breathing rate:",
                    suffix=" bpm",
                    limits=(2, None),
                    decimals=1,
                    name_label_tooltip=get_attribute_docstring(
                        BreathingProcessorConfig, "highest_breathing_rate"
                    ),
                ),
                "time_series_length_s": pidgets.FloatPidgetFactory(
                    name_label_text="Time series length:",
                    suffix=" s",
                    decimals=1,
                    name_label_tooltip=get_attribute_docstring(
                        BreathingProcessorConfig, "time_series_length_s"
                    ),
                ),
            }
        }

    @classmethod
    def _get_presence_config_pidget_mapping(cls) -> PidgetGroupFactoryMapping:
        return {
            pidgets.FlatPidgetGroup(): {
                "intra_detection_threshold": pidgets.FloatSliderPidgetFactory(
                    name_label_text="Intra detection threshold:",
                    decimals=2,
                    limits=(0, 15),
                ),
                "intra_frame_time_const": pidgets.FloatSliderPidgetFactory(
                    name_label_text="Intra time constant:",
                    suffix=" s",
                    decimals=2,
                    limits=(0, 1),
                ),
                "intra_output_time_const": pidgets.FloatSliderPidgetFactory(
                    name_label_text="Intra output time constant:",
                    suffix=" s",
                    decimals=2,
                    limits=(0.01, 20),
                    log_scale=True,
                ),
                "inter_detection_threshold": pidgets.FloatSliderPidgetFactory(
                    name_label_text="Inter detection threshold:",
                    decimals=2,
                    limits=(0, 5),
                ),
                "inter_frame_fast_cutoff": pidgets.FloatSliderPidgetFactory(
                    name_label_text="Inter fast cutoff freq.:",
                    suffix=" Hz",
                    decimals=2,
                    limits=(1, 50),
                    log_scale=True,
                ),
                "inter_frame_slow_cutoff": pidgets.FloatSliderPidgetFactory(
                    name_label_text="Inter slow cutoff freq.:",
                    suffix=" Hz",
                    decimals=2,
                    limits=(0.01, 1),
                    log_scale=True,
                ),
                "inter_frame_deviation_time_const": pidgets.FloatSliderPidgetFactory(
                    name_label_text="Inter time constant:",
                    suffix=" s",
                    decimals=2,
                    limits=(0.01, 20),
                    log_scale=True,
                ),
                "inter_output_time_const": pidgets.FloatSliderPidgetFactory(
                    name_label_text="Inter output time constant:",
                    suffix=" s",
                    decimals=2,
                    limits=(0.01, 20),
                    log_scale=True,
                ),
            }
        }

    def on_backend_state_update(self, state: Optional[SharedState]) -> None:
        if state is None:
            self.config_editor.set_data(None)
            self.sensor_config_editor.set_data(None)
            self.breathing_config_editor.set_data(None)
            self.presence_config_editor.set_data(None)
        else:
            self.sensor_id_pidget.set_data(state.sensor_id)
            self.config_editor.set_data(state.config)
            self.sensor_config_editor.set_data(state.config)
            self.breathing_config_editor.set_data(state.config.breathing_config)
            self.presence_config_editor.set_data(state.config.presence_config)

            results = state.config._collect_validation_results()

            not_handled = self.config_editor.handle_validation_results(results)

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
                self.sensor_config_editor,
                self.breathing_config_editor,
                self.presence_config_editor,
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

    def _on_breathing_config_update(self, breathing_config: BreathingProcessorConfig) -> None:
        config = self.config_editor.get_data()
        assert config is not None
        config.breathing_config = breathing_config
        BackendPlugin.update_config.rpc(self.app_model.put_task, config=config)

    def _on_presence_config_update(self, presence_config: PresenceProcessorConfig) -> None:
        config = self.config_editor.get_data()
        assert config is not None
        config.presence_config = presence_config
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


BREATHING_PLUGIN = PluginSpec(
    generation=PluginGeneration.A121,
    key="breathing",
    title="Breathing",
    docs_link="https://docs.acconeer.com/en/latest/ref_apps/a121/breathing.html",
    description="Detect breathing rate.",
    family=PluginFamily.REF_APP,
    presets=[
        PluginPresetBase(
            name="Sitting",
            description="Sitting",
            preset_id=PluginPresetId.SITTING,
        ),
        PluginPresetBase(
            name="Infant",
            description="Infant",
            preset_id=PluginPresetId.INFANT,
        ),
    ],
    default_preset_id=PluginPresetId.SITTING,
)
