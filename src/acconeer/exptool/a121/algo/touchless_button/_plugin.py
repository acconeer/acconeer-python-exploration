# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import logging
from enum import Enum, auto
from typing import Callable, Optional, Type

import numpy as np

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121.algo._plugins import (
    ProcessorBackendPluginBase,
    ProcessorBackendPluginSharedState,
    ProcessorPluginPreset,
    ProcessorViewPluginBase,
    SetupMessage,
)
from acconeer.exptool.a121.algo.touchless_button import (
    MeasurementType,
    Processor,
    ProcessorConfig,
    ProcessorResult,
    get_close_and_far_processor_config,
    get_close_and_far_sensor_config,
    get_close_processor_config,
    get_close_sensor_config,
    get_far_processor_config,
    get_far_sensor_config,
)
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
)
from acconeer.exptool.app.new.ui.plugin_components.pidgets.hooks import (
    disable_if,
    parameter_is,
)


log = logging.getLogger(__name__)


class PluginPresetId(Enum):
    CLOSE_RANGE = auto()
    FAR_RANGE = auto()
    CLOSE_AND_FAR_RANGE = auto()


class BackendPlugin(ProcessorBackendPluginBase[ProcessorConfig, ProcessorResult]):

    PLUGIN_PRESETS = {
        PluginPresetId.CLOSE_RANGE.value: lambda: ProcessorPluginPreset(
            session_config=a121.SessionConfig(get_close_sensor_config()),
            processor_config=get_close_processor_config(),
        ),
        PluginPresetId.FAR_RANGE.value: lambda: ProcessorPluginPreset(
            session_config=a121.SessionConfig(get_far_sensor_config()),
            processor_config=get_far_processor_config(),
        ),
        PluginPresetId.CLOSE_AND_FAR_RANGE.value: lambda: ProcessorPluginPreset(
            session_config=a121.SessionConfig(get_close_and_far_sensor_config()),
            processor_config=get_close_and_far_processor_config(),
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
    def get_processor_config_cls(cls) -> Type[ProcessorConfig]:
        return ProcessorConfig

    @classmethod
    def get_default_sensor_config(cls) -> a121.SensorConfig:
        return get_close_sensor_config()


class ViewPlugin(ProcessorViewPluginBase[ProcessorConfig]):
    @classmethod
    def get_pidget_mapping(cls) -> PidgetFactoryMapping:

        return {
            "sensitivity_close": pidgets.FloatPidgetFactory(
                name_label_text="Sensitivity (close range):",
                decimals=1,
                limits=(0.1, 4),
                hooks=disable_if(parameter_is("measurement_type", MeasurementType.FAR_RANGE)),
            ),
            "patience_close": pidgets.IntPidgetFactory(
                name_label_text="Patience (close range):",
                limits=(0, None),
                hooks=disable_if(parameter_is("measurement_type", MeasurementType.FAR_RANGE)),
            ),
            "sensitivity_far": pidgets.FloatPidgetFactory(
                name_label_text="Sensitivity (far range):",
                decimals=1,
                limits=(0.1, 4),
                hooks=disable_if(parameter_is("measurement_type", MeasurementType.CLOSE_RANGE)),
            ),
            "patience_far": pidgets.IntPidgetFactory(
                name_label_text="Patience (far range):",
                limits=(0, None),
                hooks=disable_if(parameter_is("measurement_type", MeasurementType.CLOSE_RANGE)),
            ),
            "calibration_duration_s": pidgets.FloatPidgetFactory(
                name_label_text="Calibration duration:",
                suffix="s",
                limits=(0, None),
            ),
            "calibration_interval_s": pidgets.FloatPidgetFactory(
                name_label_text="Calibration interval:",
                suffix="s",
                limits=(1, None),
            ),
            "measurement_type": pidgets.EnumPidgetFactory(
                enum_type=MeasurementType,
                name_label_text="Range:",
                label_mapping={
                    MeasurementType.CLOSE_RANGE: "Close",
                    MeasurementType.FAR_RANGE: "Far",
                    MeasurementType.CLOSE_AND_FAR_RANGE: "Close and far",
                },
            ),
        }

    @classmethod
    def get_processor_config_cls(cls) -> Type[ProcessorConfig]:
        return ProcessorConfig

    @classmethod
    def supports_multiple_subsweeps(self) -> bool:
        return True


class PlotPlugin(PgPlotPlugin):
    def __init__(self, app_model: AppModel) -> None:
        super().__init__(app_model=app_model)
        self._plot_job: Optional[ProcessorResult] = None
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

        self.detection_history_plot = self._create_detection_plot(self.plot_layout)

        self.detection_history_curve_close = self.detection_history_plot.plot(
            pen=et.utils.pg_pen_cycler(1, width=5)
        )
        self.detection_history_curve_far = self.detection_history_plot.plot(
            pen=et.utils.pg_pen_cycler(0, width=5)
        )

        close_html = (
            '<div style="text-align: center">'
            '<span style="color: #FFFFFF;font-size:15pt;">'
            "{}</span></div>".format("Close detection")
        )
        far_html = (
            '<div style="text-align: center">'
            '<span style="color: #FFFFFF;font-size:15pt;">'
            "{}</span></div>".format("Far detection")
        )
        self.close_text_item = pg.TextItem(
            html=close_html,
            fill=pg.mkColor(0xFF, 0x7F, 0x0E),
            anchor=(0.5, 0),
        )
        self.far_text_item = pg.TextItem(
            html=far_html,
            fill=pg.mkColor(0x1F, 0x77, 0xB4),
            anchor=(0.5, 0),
        )
        pos_left = (100 / 3, 1.8)
        pos_right = (2 * 100 / 3, 1.8)
        self.close_text_item.setPos(*pos_left)
        self.far_text_item.setPos(*pos_right)
        self.detection_history_plot.addItem(self.close_text_item)
        self.detection_history_plot.addItem(self.far_text_item)
        self.close_text_item.hide()
        self.far_text_item.hide()

        self.detection_history = np.full((2, 100), np.NaN)

    def draw_plot_job(self, processor_result: ProcessorResult) -> None:
        detection = np.array([processor_result.detection_close, processor_result.detection_far])
        self.detection_history = np.roll(self.detection_history, -1, axis=1)
        self.detection_history[:, -1] = detection

        self.detection_history_curve_close.setData(self.detection_history[0])
        self.detection_history_curve_far.setData(self.detection_history[1])

        if processor_result.detection_close:
            self.close_text_item.show()
        else:
            self.close_text_item.hide()

        if processor_result.detection_far:
            self.far_text_item.show()
        else:
            self.far_text_item.hide()

    @staticmethod
    def _create_detection_plot(parent: pg.GraphicsLayout) -> pg.PlotItem:
        detection_history_plot = parent.addPlot()
        detection_history_plot.setMenuEnabled(False)
        detection_history_plot.setMouseEnabled(x=False, y=False)
        detection_history_plot.hideButtons()
        detection_history_plot.showGrid(x=True, y=True, alpha=0.5)
        detection_history_plot.setYRange(-0.1, 1.8)
        return detection_history_plot


class PluginSpec(PluginSpecBase):
    def create_backend_plugin(
        self, callback: Callable[[Message], None], key: str
    ) -> BackendPlugin:
        return BackendPlugin(callback=callback, generation=self.generation, key=key)

    def create_view_plugin(self, app_model: AppModel) -> ViewPlugin:
        return ViewPlugin(app_model=app_model)

    def create_plot_plugin(self, app_model: AppModel) -> PlotPlugin:
        return PlotPlugin(app_model=app_model)


TOUCHLESS_BUTTON_PLUGIN = PluginSpec(
    generation=PluginGeneration.A121,
    key="touchless_button",
    title="Touchless button",
    description="Detect tap/wave motion and register as button press.",
    family=PluginFamily.EXAMPLE_APP,
    presets=[
        PluginPresetBase(
            name="Close range",
            description="Close range",
            preset_id=PluginPresetId.CLOSE_RANGE,
        ),
        PluginPresetBase(
            name="Far range",
            description="Far range",
            preset_id=PluginPresetId.FAR_RANGE,
        ),
        PluginPresetBase(
            name="Close and far range",
            description="Close and far range",
            preset_id=PluginPresetId.CLOSE_AND_FAR_RANGE,
        ),
    ],
    default_preset_id=PluginPresetId.CLOSE_RANGE,
)
