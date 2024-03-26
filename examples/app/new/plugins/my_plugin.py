# Copyright (c) Acconeer AB, 2024
# All rights reserved

from __future__ import annotations

import logging
import typing as t
from enum import Enum, auto

import attrs
import numpy as np
import numpy.typing as npt

import pyqtgraph as pg

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import AlgoParamEnum, AlgoProcessorConfigBase, ProcessorBase
from acconeer.exptool.a121.algo._plugins import (
    ProcessorBackendPluginBase,
    ProcessorBackendPluginSharedState,
    ProcessorPluginPreset,
    ProcessorViewPluginBase,
    SetupMessage,
)
from acconeer.exptool.a121.algo._utils import get_distances_m
from acconeer.exptool.app.new import (
    AppModel,
    Message,
    PgPlotPlugin,
    PidgetFactoryMapping,
    PluginFamily,
    PluginGeneration,
    PluginPresetBase,
    PluginSpecBase,
    backend,
    pidgets,
    register_plugin,
)


log = logging.getLogger(__name__)


class PluginPresetId(Enum):
    DEFAULT = auto()


class PlotColor(AlgoParamEnum):
    ACCONEER_BLUE = "#38bff0"
    WHITE = "#ffffff"
    BLACK = "#000000"
    PINK = "#f280a1"


@attrs.mutable(kw_only=True)
class ProcessorConfig(AlgoProcessorConfigBase):
    plot_color: PlotColor = attrs.field(default=PlotColor.ACCONEER_BLUE, converter=PlotColor)
    """What color the plot graph should be."""

    scale: float = attrs.field(default=1.0)
    """Allows you to scale the incoming amplitude by a factor."""

    def _collect_validation_results(
        self, config: a121.SessionConfig
    ) -> t.List[a121.ValidationResult]:
        return []


@attrs.frozen(kw_only=True)
class ProcessorResult:
    scaled_mean_abs: npt.NDArray = attrs.field(default=np.array([]))
    plot_color: PlotColor = attrs.field(default=PlotColor.ACCONEER_BLUE)


class Processor(ProcessorBase[ProcessorResult]):
    def __init__(
        self,
        *,
        sensor_config: a121.SensorConfig,
        metadata: a121.Metadata,
        processor_config: ProcessorConfig,
    ) -> None:
        self._scale = processor_config.scale
        self._plot_color = processor_config.plot_color

    def process(self, result: a121.Result) -> ProcessorResult:
        frame = result.frame
        mean_sweep = frame.mean(axis=0)
        abs_mean_sweep = np.abs(mean_sweep)
        return ProcessorResult(
            scaled_mean_abs=self._scale * abs_mean_sweep, plot_color=self._plot_color
        )


class BackendPlugin(ProcessorBackendPluginBase):
    PLUGIN_PRESETS = {
        PluginPresetId.DEFAULT.value: lambda: ProcessorPluginPreset(
            session_config=a121.SessionConfig(),
            processor_config=ProcessorConfig(),
        ),
    }

    @classmethod
    def get_processor(cls, state: ProcessorBackendPluginSharedState[ProcessorConfig]) -> Processor:
        if state.metadata is None:
            raise RuntimeError("metadata is None")

        if isinstance(state.metadata, list):
            raise RuntimeError("metadata is unexpectedly extended")

        return Processor(
            sensor_config=state.session_config.sensor_config,
            processor_config=state.processor_config,
            metadata=state.metadata,
        )

    @classmethod
    def get_processor_config_cls(cls) -> t.Type[ProcessorConfig]:
        return ProcessorConfig

    @classmethod
    def get_default_sensor_config(cls) -> a121.SensorConfig:
        return a121.SensorConfig()


class ViewPlugin(ProcessorViewPluginBase):
    @classmethod
    def get_pidget_mapping(cls) -> PidgetFactoryMapping:
        return {
            "plot_color": pidgets.EnumPidgetFactory(
                enum_type=PlotColor,
                name_label_text="Plot color:",
                name_label_tooltip="What color the plot graph should be",
                label_mapping={
                    PlotColor.ACCONEER_BLUE: "Acconeer Blue",
                    PlotColor.WHITE: "White",
                    PlotColor.BLACK: "Black",
                    PlotColor.PINK: "Pink",
                },
            ),
            "scale": pidgets.FloatSliderPidgetFactory(
                name_label_text="Scale:",
                name_label_tooltip="Allows you to scale the incoming amplitude by a factor",
                suffix="",
                limits=(0.001, 1.0),
                decimals=3,
            ),
        }

    @classmethod
    def get_processor_config_cls(cls) -> t.Type[ProcessorConfig]:
        return ProcessorConfig


class PlotPlugin(PgPlotPlugin):
    def __init__(self, app_model: AppModel) -> None:
        super().__init__(app_model=app_model)
        self._plot_job: t.Optional[ProcessorResult] = None
        self._is_setup = False

    def handle_message(self, message: backend.GeneralMessage) -> None:
        if isinstance(message, backend.PlotMessage):
            self._plot_job = message.result
        elif isinstance(message, SetupMessage):
            if isinstance(message.metadata, list):
                raise RuntimeError("Metadata is unexpectedly extended")

            self.setup(
                metadata=message.metadata,
                sensor_config=message.session_config.sensor_config,
            )
            self._is_setup = True
        else:
            log.warn(f"{self.__class__.__name__} got an unsupported command: {message.name!r}.")

    def draw(self) -> None:
        if not self._is_setup or self._plot_job is None:
            return

        try:
            self.draw_plot_job(processor_result=self._plot_job)
        finally:
            self._plot_job = None

    def setup(self, metadata: a121.Metadata, sensor_config: a121.SensorConfig) -> None:
        self.plot_layout.clear()
        self._distances_m = get_distances_m(sensor_config, metadata)

        # amplitude plot
        self.ampl_plot = pg.PlotItem()
        self.ampl_plot.setMenuEnabled(False)
        self.ampl_plot.showGrid(x=False, y=True)
        self.ampl_plot.setLabel("left", "Amplitude")
        self.ampl_plot.setLabel("bottom", "Distance (m)")
        self.ampl_curve = self.ampl_plot.plot()

        sublayout = self.plot_layout.addLayout()
        sublayout.addItem(self.ampl_plot)

    def draw_plot_job(self, processor_result: ProcessorResult) -> None:
        self.ampl_plot.setYRange(0, processor_result.scaled_mean_abs.max())
        self.ampl_curve.setData(
            self._distances_m,
            processor_result.scaled_mean_abs,
            pen=pg.mkPen(processor_result.plot_color.value, width=2),
        )


class PluginSpec(PluginSpecBase):
    def create_backend_plugin(
        self, callback: t.Callable[[Message], None], key: str
    ) -> BackendPlugin:
        return BackendPlugin(callback=callback, generation=self.generation, key=key)

    def create_view_plugin(self, app_model: AppModel) -> ViewPlugin:
        return ViewPlugin(app_model=app_model)

    def create_plot_plugin(self, app_model: AppModel) -> PlotPlugin:
        return PlotPlugin(app_model=app_model)


MY_PLUGIN = PluginSpec(
    generation=PluginGeneration.A121,
    key="my_plugin",
    title="My Plugin",
    description="My plugin.",
    family=PluginFamily.EXTERNAL_PLUGIN,
    presets=[
        PluginPresetBase(name="Default", preset_id=PluginPresetId.DEFAULT),
    ],
    default_preset_id=PluginPresetId.DEFAULT,
)


def register() -> None:
    register_plugin(MY_PLUGIN)
