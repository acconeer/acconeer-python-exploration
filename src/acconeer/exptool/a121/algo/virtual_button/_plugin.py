# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from typing import Type

import numpy as np

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121.algo._plugins import (
    ProcessorBackendPluginBase,
    ProcessorPlotPluginBase,
    ProcessorViewPluginBase,
)
from acconeer.exptool.a121.algo.virtual_button import (
    Processor,
    ProcessorConfig,
    ProcessorResult,
    get_sensor_config,
)
from acconeer.exptool.app.new import AppModel, Plugin, PluginFamily, PluginGeneration
from acconeer.exptool.app.new.ui.plugin import PidgetFactoryMapping, pidgets


class BackendPlugin(ProcessorBackendPluginBase[ProcessorConfig, ProcessorResult]):
    @classmethod
    def get_processor_cls(cls) -> Type[Processor]:
        return Processor

    @classmethod
    def get_processor_config_cls(cls) -> Type[ProcessorConfig]:
        return ProcessorConfig

    @classmethod
    def get_default_sensor_config(cls) -> a121.SensorConfig:
        return get_sensor_config()


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


VIRTUAL_BUTTON_PLUGIN = Plugin(
    generation=PluginGeneration.A121,
    key="virtual_button",
    title="Virtual button",
    description=None,
    family=PluginFamily.EXAMPLE_APP,
    backend_plugin=BackendPlugin,
    plot_plugin=PlotPlugin,
    view_plugin=ViewPlugin,
)
