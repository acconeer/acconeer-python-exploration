# Copyright (c) Acconeer AB, 2022-2025
# All rights reserved

from __future__ import annotations

import logging
from enum import Enum, auto
from typing import Any, Callable, List, Optional, Type, Union

import numpy as np
import numpy.typing as npt

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool._core.docstrings import get_attribute_docstring
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
    RangeResult,
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
from acconeer.exptool.app.new.ui.components.pidgets.hooks import (
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
            msg = "metadata is None"
            raise RuntimeError(msg)

        if isinstance(state.metadata, list):
            msg = "metadata is unexpectedly extended"
            raise RuntimeError(msg)

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
                name_label_tooltip=get_attribute_docstring(ProcessorConfig, "sensitivity_close"),
                decimals=1,
                limits=(0.1, 4),
                hooks=disable_if(parameter_is("measurement_type", MeasurementType.FAR_RANGE)),
            ),
            "patience_close": pidgets.IntPidgetFactory(
                name_label_text="Patience (close range):",
                name_label_tooltip=get_attribute_docstring(ProcessorConfig, "patience_close"),
                limits=(0, None),
                hooks=disable_if(parameter_is("measurement_type", MeasurementType.FAR_RANGE)),
            ),
            "sensitivity_far": pidgets.FloatPidgetFactory(
                name_label_text="Sensitivity (far range):",
                name_label_tooltip=get_attribute_docstring(ProcessorConfig, "sensitivity_far"),
                decimals=1,
                limits=(0.1, 4),
                hooks=disable_if(parameter_is("measurement_type", MeasurementType.CLOSE_RANGE)),
            ),
            "patience_far": pidgets.IntPidgetFactory(
                name_label_text="Patience (far range):",
                name_label_tooltip=get_attribute_docstring(ProcessorConfig, "patience_far"),
                limits=(0, None),
                hooks=disable_if(parameter_is("measurement_type", MeasurementType.CLOSE_RANGE)),
            ),
            "calibration_duration_s": pidgets.FloatPidgetFactory(
                name_label_text="Calibration duration:",
                name_label_tooltip=get_attribute_docstring(
                    ProcessorConfig, "calibration_duration_s"
                ),
                suffix="s",
                limits=(0, None),
            ),
            "calibration_interval_s": pidgets.FloatPidgetFactory(
                name_label_text="Calibration interval:",
                name_label_tooltip=get_attribute_docstring(
                    ProcessorConfig, "calibration_interval_s"
                ),
                suffix="s",
                limits=(1, None),
            ),
            "measurement_type": pidgets.EnumPidgetFactory(
                enum_type=MeasurementType,
                name_label_text="Range:",
                name_label_tooltip=get_attribute_docstring(ProcessorConfig, "measurement_type"),
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
    score_history_close: Optional[npt.NDArray[np.float64]]
    score_history_far: Optional[npt.NDArray[np.float64]]
    score_history_curves_close: Optional[npt.NDArray[np.object_]]
    score_history_curves_far: Optional[npt.NDArray[np.object_]]
    score_history_curves: Union[List[npt.NDArray[Any]], npt.NDArray[Any]]

    def __init__(self, app_model: AppModel) -> None:
        super().__init__(app_model=app_model)
        self._plot_job: Optional[ProcessorResult] = None
        self._is_setup = False

    def handle_message(self, message: backend.GeneralMessage) -> None:
        if isinstance(message, backend.PlotMessage):
            self._plot_job = message.result
        elif isinstance(message, SetupMessage):
            if isinstance(message.metadata, list):
                msg = "Metadata is unexpectedly extended"
                raise RuntimeError(msg)

            self.setup(
                metadata=message.metadata,
                sensor_config=message.session_config.sensor_config,
                processor_config=message.processor_config,
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

    def setup(
        self,
        metadata: a121.Metadata,
        sensor_config: a121.SensorConfig,
        processor_config: ProcessorConfig,
    ) -> None:
        self.plot_layout.clear()

        self.detection_history_plot = self._create_detection_plot(self.plot_layout)
        detection_plot_legend = self.detection_history_plot.legend

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

        self.detection_history = np.full((2, 100), np.nan)

        self.score_history_plot = self._create_score_plot(self.plot_layout)
        score_plot_legend = self.score_history_plot.legend
        self.score_smooth_max = et.utils.SmoothMax()

        self.threshold_history_curve_close = self.score_history_plot.plot(
            pen=et.utils.pg_pen_cycler(1, width=2.5, style="--"),
        )
        self.threshold_history_curve_far = self.score_history_plot.plot(
            pen=et.utils.pg_pen_cycler(0, width=2.5, style="--"),
        )

        self.threshold_history = np.full((2, 100), np.nan)

        cycle_index = 2  # To not have same colors as thresholds
        if processor_config.measurement_type == MeasurementType.CLOSE_RANGE:
            measurement_type = "Close"
            score_plot_legend.addItem(self.threshold_history_curve_close, "Close range threshold")
            detection_plot_legend.addItem(self.detection_history_curve_close, "Close range")
        elif processor_config.measurement_type == MeasurementType.FAR_RANGE:
            measurement_type = "Far"
            score_plot_legend.addItem(self.threshold_history_curve_far, "Far range threshold")
            detection_plot_legend.addItem(self.detection_history_curve_far, "Far range")

        if processor_config.measurement_type != MeasurementType.CLOSE_AND_FAR_RANGE:
            score_history = np.full((sensor_config.subsweep.num_points, 100), np.nan)
            score_history_curves = np.empty((sensor_config.subsweep.num_points,), dtype=object)
            for i in range(sensor_config.subsweep.num_points):
                score_history_curves[i] = pg.ScatterPlotItem(
                    brush=et.utils.pg_brush_cycler(cycle_index),
                    name=f"{measurement_type} range, point {i}",
                )
                self.score_history_plot.addItem(score_history_curves[i])
                cycle_index += 1

            if processor_config.measurement_type == MeasurementType.CLOSE_RANGE:
                self.score_history_close = score_history
                self.score_history_curves_close = score_history_curves
                self.score_history_far = None
                self.score_history_curves_far = None
            elif processor_config.measurement_type == MeasurementType.FAR_RANGE:
                self.score_history_close = None
                self.score_history_curves_close = None
                self.score_history_far = score_history
                self.score_history_curves_far = score_history_curves

        elif processor_config.measurement_type == MeasurementType.CLOSE_AND_FAR_RANGE:
            score_plot_legend.addItem(self.threshold_history_curve_close, "Close range threshold")
            score_plot_legend.addItem(self.threshold_history_curve_far, "Far range threshold")
            detection_plot_legend.addItem(self.detection_history_curve_close, "Close range")
            detection_plot_legend.addItem(self.detection_history_curve_far, "Far range")
            self.score_history_close = np.full(
                (sensor_config.subsweeps[0].num_points, 100), np.nan
            )
            self.score_history_far = np.full((sensor_config.subsweeps[1].num_points, 100), np.nan)
            self.score_history_curves_close = np.empty(
                (sensor_config.subsweeps[0].num_points,), dtype=object
            )
            self.score_history_curves_far = np.empty(
                (sensor_config.subsweeps[1].num_points,), dtype=object
            )

            range_labels = ["Close", "Far"]
            for n, subsweep in enumerate(sensor_config.subsweeps):
                measurement_type = range_labels[n]
                score_history_curve_list = [
                    self.score_history_curves_close,
                    self.score_history_curves_far,
                ]
                for i in range(subsweep.num_points):
                    score_history_curve_list[n][i] = pg.ScatterPlotItem(
                        brush=et.utils.pg_brush_cycler(cycle_index),
                        name=f"{measurement_type} range, point {i}",
                    )
                    self.score_history_plot.addItem(score_history_curve_list[n][i])
                    cycle_index += 1
            self.score_history_curves_close = score_history_curve_list[0]
            self.score_history_curves_far = score_history_curve_list[1]

    def draw_plot_job(self, processor_result: ProcessorResult) -> None:
        def is_none_or_detection(x: Optional[RangeResult]) -> Optional[bool]:
            return x.detection if x is not None else None

        detection = np.array(
            [
                is_none_or_detection(processor_result.close),
                is_none_or_detection(processor_result.far),
            ]
        )
        self.detection_history = np.roll(self.detection_history, -1, axis=1)
        self.detection_history[:, -1] = detection

        self.detection_history_curve_close.setData(self.detection_history[0])
        self.detection_history_curve_far.setData(self.detection_history[1])

        if processor_result.close is not None:
            if processor_result.close.detection:
                self.close_text_item.show()
            else:
                self.close_text_item.hide()

        if processor_result.far is not None:
            if processor_result.far.detection:
                self.far_text_item.show()
            else:
                self.far_text_item.hide()

        max_val = 0.0

        def is_none_or_threshold(x: Optional[RangeResult]) -> Optional[float]:
            return x.threshold if x is not None else None

        threshold = np.array(
            [
                is_none_or_threshold(processor_result.close),
                is_none_or_threshold(processor_result.far),
            ]
        )
        if np.nanmax(np.array(threshold, dtype=float)) > max_val:
            max_val = np.nanmax(np.array(threshold, dtype=float))
        self.threshold_history = np.roll(self.threshold_history, -1, axis=1)
        self.threshold_history[:, -1] = threshold

        self.threshold_history_curve_close.setData(self.threshold_history[0])
        self.threshold_history_curve_far.setData(self.threshold_history[1])

        if self.score_history_close is not None:
            self.score_history_close = np.roll(self.score_history_close, -1, axis=1)
            assert processor_result.close is not None
            # Plot the second highest score
            self.score_history_close[:, -1] = np.sort(processor_result.close.score, axis=0)[-2, :]

            assert self.score_history_curves_close is not None
            for i, curve in enumerate(self.score_history_curves_close):
                # Assign x-values so that setData() doesn't give error when y-values are NaN
                curve.setData(np.arange(0, 100), self.score_history_close[i, :].flatten())

            if np.max(processor_result.close.score) > max_val:
                max_val = float(np.max(processor_result.close.score))

        if self.score_history_far is not None:
            self.score_history_far = np.roll(self.score_history_far, -1, axis=1)
            assert processor_result.far is not None
            # Plot the second highest score
            self.score_history_far[:, -1] = np.sort(processor_result.far.score, axis=0)[-2, :]

            assert self.score_history_curves_far is not None
            for i, curve in enumerate(self.score_history_curves_far):
                # Assign x-values so that setData() doesn't give error when y-values are NaN
                curve.setData(np.arange(0, 100), self.score_history_far[i, :].flatten())

            if np.max(processor_result.far.score) > max_val:
                max_val = float(np.max(processor_result.far.score))

        if max_val != 0.0:
            self.score_history_plot.setYRange(0.0, self.score_smooth_max.update(max_val))

    @staticmethod
    def _create_detection_plot(parent: pg.GraphicsLayout) -> pg.PlotItem:
        detection_history_plot = parent.addPlot(row=0, col=0)
        detection_history_plot.setTitle("Detection")
        detection_history_plot.setLabel(axis="bottom", text="Frames")
        detection_history_plot.addLegend()
        detection_history_plot.setMenuEnabled(False)
        detection_history_plot.setMouseEnabled(x=False, y=False)
        detection_history_plot.hideButtons()
        detection_history_plot.showGrid(x=True, y=True, alpha=0.5)
        detection_history_plot.setYRange(-0.1, 1.8)
        return detection_history_plot

    @staticmethod
    def _create_score_plot(parent: pg.GraphicsLayout) -> pg.PlotItem:
        score_history_plot = parent.addPlot(row=1, col=0)
        score_history_plot.setTitle("Detection score")
        score_history_plot.setLabel(axis="bottom", text="Frames")
        score_history_plot.addLegend()
        score_history_plot.setMenuEnabled(False)
        score_history_plot.setMouseEnabled(x=False, y=False)
        score_history_plot.hideButtons()
        score_history_plot.showGrid(x=True, y=True, alpha=0.5)
        return score_history_plot


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
    docs_link="https://docs.acconeer.com/en/latest/ref_apps/a121/touchless_button.html",
    description="Detect tap/wave motion and register as button press.",
    family=PluginFamily.REF_APP,
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
