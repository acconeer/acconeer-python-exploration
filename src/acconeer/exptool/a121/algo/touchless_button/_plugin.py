# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from enum import Enum, auto
from typing import Callable, Type

import numpy as np

from PySide6.QtWidgets import QWidget

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121.algo._plugins import (
    ProcessorBackendPluginBase,
    ProcessorPlotPluginBase,
    ProcessorPluginPreset,
    ProcessorViewPluginBase,
)
from acconeer.exptool.a121.algo.touchless_button import (
    Processor,
    ProcessorConfig,
    ProcessorResult,
    get_close_and_far_processor_config,
    get_close_and_far_sensor_config,
    get_close_processor_config,
    get_close_sensor_config,
)
from acconeer.exptool.app.new import (
    AppModel,
    Message,
    PidgetFactoryMapping,
    PluginFamily,
    PluginGeneration,
    PluginPresetBase,
    PluginSpecBase,
    pidgets,
)


class PluginPresetId(Enum):
    CLOSE_RANGE = auto()
    CLOSE_AND_FAR_RANGE = auto()


class BackendPlugin(ProcessorBackendPluginBase[ProcessorConfig, ProcessorResult]):

    PLUGIN_PRESETS = {
        PluginPresetId.CLOSE_RANGE.value: lambda: ProcessorPluginPreset(
            session_config=a121.SessionConfig(get_close_sensor_config()),
            processor_config=get_close_processor_config(),
        ),
        PluginPresetId.CLOSE_AND_FAR_RANGE.value: lambda: ProcessorPluginPreset(
            session_config=a121.SessionConfig(get_close_and_far_sensor_config()),
            processor_config=get_close_and_far_processor_config(),
        ),
    }

    @classmethod
    def get_processor_cls(cls) -> Type[Processor]:
        return Processor

    @classmethod
    def get_processor_config_cls(cls) -> Type[ProcessorConfig]:
        return ProcessorConfig

    @classmethod
    def get_default_sensor_config(cls) -> a121.SensorConfig:
        return get_close_sensor_config()


class ViewPlugin(ProcessorViewPluginBase[ProcessorConfig]):
    @classmethod
    def get_pidget_mapping(cls) -> PidgetFactoryMapping:
        # Note: Incomplete mapping
        return {
            "sensitivity_close": pidgets.FloatParameterWidgetFactory(
                name_label_text="Sensitivity",
                decimals=1,
                limits=(0.1, 4),
            ),
            "patience_close": pidgets.IntParameterWidgetFactory(
                name_label_text="Patience",
                limits=(0, None),
            ),
            "calibration_duration_s": pidgets.FloatParameterWidgetFactory(
                name_label_text="Calibration duration",
                suffix="s",
                limits=(0, None),
            ),
            "calibration_interval_s": pidgets.FloatParameterWidgetFactory(
                name_label_text="Calibration interval",
                suffix="s",
                limits=(1, None),
            ),
        }

    @classmethod
    def get_processor_config_cls(cls) -> Type[ProcessorConfig]:
        return ProcessorConfig


class PlotPlugin(ProcessorPlotPluginBase[ProcessorResult]):
    def __init__(self, *, plot_layout: pg.GraphicsLayout, app_model: AppModel) -> None:
        super().__init__(plot_layout=plot_layout, app_model=app_model)

    def setup(self, metadata: a121.Metadata, sensor_config: a121.SensorConfig) -> None:
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

    def update(self, processor_result: ProcessorResult) -> None:
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

    def create_view_plugin(self, app_model: AppModel, view_widget: QWidget) -> ViewPlugin:
        return ViewPlugin(app_model=app_model, view_widget=view_widget)

    def create_plot_plugin(
        self, app_model: AppModel, plot_layout: pg.GraphicsLayout
    ) -> PlotPlugin:
        return PlotPlugin(app_model=app_model, plot_layout=plot_layout)


TOUCHLESS_BUTTON_PLUGIN = PluginSpec(
    generation=PluginGeneration.A121,
    key="touchless_button",
    title="Touchless button",
    description="Detect tap/wave motion and register as button press.",
    family=PluginFamily.EXAMPLE_APP,
    presets=[
        PluginPresetBase(
            name="Close Range",
            description="Close range",
            preset_id=PluginPresetId.CLOSE_RANGE,
        ),
        PluginPresetBase(
            name="Close and far range",
            description="Close and far range",
            preset_id=PluginPresetId.CLOSE_AND_FAR_RANGE,
        ),
    ],
    default_preset_id=PluginPresetId.CLOSE_RANGE,
)
