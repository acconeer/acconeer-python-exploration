# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved

from __future__ import annotations

import itertools
import logging
from enum import Enum, auto
from typing import Callable, Dict, List, Optional, Type, TypeVar

import numpy as np
import numpy.typing as npt

from PySide6 import QtCore
from PySide6.QtGui import QTransform
from PySide6.QtWidgets import (
    QVBoxLayout,
)

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121 import algo
from acconeer.exptool.a121._core import utils as core_utils
from acconeer.exptool.a121.algo._plugins import (
    ExtendedProcessorBackendPluginBase,
    ProcessorBackendPluginSharedState,
    ProcessorPluginPreset,
    ProcessorPluginSpec,
    ProcessorViewPluginBase,
    SetupMessage,
)
from acconeer.exptool.app.new import (
    AppModel,
    Message,
    PidgetFactoryMapping,
    PlotPluginBase,
    PluginFamily,
    PluginGeneration,
    PluginPresetBase,
    backend,
    pidgets,
)
from acconeer.exptool.app.new.ui.components import GotoResourceTabButton, TabPGWidget

from ._processor import (
    AmplitudeMethod,
    Processor,
    ProcessorConfig,
    ProcessorResult,
    get_sensor_config,
)


log = logging.getLogger(__name__)


_T = TypeVar("_T")


class PluginPresetId(Enum):
    DEFAULT = auto()


SEMI_TRANSPARENT_BRUSH = pg.mkBrush(color=(0xFF, 0xFF, 0xFF, int(0.8 * 0xFF)))


class BackendPlugin(ExtendedProcessorBackendPluginBase[ProcessorConfig, ProcessorResult]):
    PLUGIN_PRESETS = {
        PluginPresetId.DEFAULT.value: lambda: ProcessorPluginPreset(
            session_config=a121.SessionConfig(get_sensor_config()),
            processor_config=BackendPlugin.get_processor_config_cls()(),
        ),
    }

    @classmethod
    def get_processor(cls, state: ProcessorBackendPluginSharedState[ProcessorConfig]) -> Processor:
        return Processor(
            session_config=state.session_config,
            processor_config=state.processor_config,
        )

    @classmethod
    def get_processor_config_cls(cls) -> Type[ProcessorConfig]:
        return ProcessorConfig

    @classmethod
    def get_default_sensor_config(cls) -> a121.SensorConfig:
        return get_sensor_config()


class ViewPlugin(ProcessorViewPluginBase[ProcessorConfig]):
    def __init__(self, app_model: AppModel) -> None:
        super().__init__(app_model=app_model)

        goto_resource_button = GotoResourceTabButton()
        goto_resource_button.clicked.connect(
            lambda: app_model.sig_resource_tab_input_block_requested.emit(
                self.session_config_editor.get_data()
            )
        )
        self.scrolly_layout.insertWidget(0, goto_resource_button)

    @classmethod
    def get_pidget_mapping(cls) -> PidgetFactoryMapping:
        return {
            "amplitude_method": pidgets.EnumPidgetFactory(
                enum_type=AmplitudeMethod,
                name_label_text="Amplitude method:",
                name_label_tooltip=(
                    "The method used to calculate the amplitude from the complex Sparse IQ data"
                ),
                label_mapping={
                    AmplitudeMethod.COHERENT: "Coherent",
                    AmplitudeMethod.NONCOHERENT: "Non-coherent",
                    AmplitudeMethod.FFT_MAX: "FFT Max",
                },
            )
        }

    @classmethod
    def get_processor_config_cls(cls) -> Type[ProcessorConfig]:
        return ProcessorConfig

    @classmethod
    def supports_multiple_subsweeps(self) -> bool:
        return True

    @classmethod
    def supports_multiple_sensors(self) -> bool:
        return True


_Extended = List[Dict[int, _T]]


class PlotPlugin(PlotPluginBase):
    def __init__(self, app_model: AppModel) -> None:
        super().__init__(app_model=app_model)

        self.smooth_max = et.utils.SmoothMax()
        self._plot_job: Optional[ProcessorResult] = None
        self._is_setup = False
        self.ampl_plot: Optional[pg.PlotItem] = None

        self.ampl_curves: _Extended[list[pg.PlotDataItem]] = []
        self.subsweeps_distances_m: _Extended[list[npt.NDArray[np.float64]]] = []

        layout = QVBoxLayout()

        self.amplitude_plot_widget = pg.GraphicsLayoutWidget()

        self.tab_widget = TabPGWidget()

        layout.addWidget(self.amplitude_plot_widget, stretch=1)
        layout.addWidget(self.tab_widget, stretch=2)

        self.setLayout(layout)
        self.tab_widget.setVisible(False)

    def handle_message(self, message: backend.GeneralMessage) -> None:
        if isinstance(message, backend.PlotMessage):
            self._plot_job = message.result
        elif isinstance(message, SetupMessage):
            if isinstance(message.metadata, a121.Metadata):
                metadata = [{message.session_config.sensor_id: message.metadata}]
            else:
                metadata = message.metadata

            self.setup(
                metadatas=metadata,
                session_config=message.session_config,
            )
            self._is_setup = True
            self.tab_widget.setVisible(True)
        else:
            log.warn(f"{self.__class__.__name__} got an unsupported command: {message.name!r}.")

    def draw(self) -> None:
        if not self._is_setup or self._plot_job is None:
            return

        try:
            self.draw_plot_job(processor_result=self._plot_job)
        finally:
            self._plot_job = None

    def draw_plot_job(self, processor_result: ProcessorResult) -> None:
        if self.ampl_plot is None:
            raise RuntimeError

        max_ = 0.0

        for (
            plot_data_items,
            entry_result,
            subsweeps_distances_m,
        ) in core_utils.iterate_extended_structure_values(
            core_utils.zip3_extended_structures(
                core_utils.zip3_extended_structures(
                    self.ampl_curves, self.phase_curves, self.ft_images
                ),
                processor_result,
                self.subsweeps_distances_m,
            )
        ):
            for (
                amplitude_curve,
                phase_curve,
                ft_image,
                subsweep_result,
                subsweep_distances_m,
            ) in zip(*plot_data_items, entry_result, subsweeps_distances_m):
                ampls = subsweep_result.amplitudes
                amplitude_curve.setData(subsweep_distances_m, ampls)
                max_ = max(max_, np.max(ampls).item())

                phase_curve.setData(subsweep_distances_m, subsweep_result.phases)

                dvm = subsweep_result.distance_velocity_map
                ft_image.updateImage(dvm.T, levels=(0, 1.05 * np.max(dvm)))

        self.ampl_plot.setYRange(0, self.smooth_max.update(max_))

    def setup(
        self, metadatas: list[dict[int, a121.Metadata]], session_config: a121.SessionConfig
    ) -> None:
        self.amplitude_plot_widget.ci.clear()
        self.tab_widget.clear()

        self.subsweeps_distances_m = core_utils.map_over_extended_structure(
            lambda args: self._get_distances_m(*args),
            core_utils.zip_extended_structures(session_config.groups, metadatas),
        )

        self._setup_amplitude(session_config)
        self._setup_phase_and_dvm(session_config, metadatas)

    @staticmethod
    def _get_distances_m(
        config: a121.SensorConfig, metadata: a121.Metadata
    ) -> list[npt.NDArray[np.float64]]:
        return [algo.get_distances_m(subsweep, metadata) for subsweep in config.subsweeps]

    def _setup_amplitude(self, session_config: a121.SessionConfig) -> None:
        counter = itertools.count(0)

        entry_serial_numbers = core_utils.map_over_extended_structure(
            lambda _: next(counter), session_config.groups
        )
        shape = core_utils.extended_structure_shape(session_config.groups)
        sensor_ids = [{sensor_id: sensor_id for sensor_id in group} for group in shape]
        group_idxs = [
            {sensor_id: group_idx for sensor_id in group} for group_idx, group in enumerate(shape)
        ]

        num_unique_sensors = len(set(core_utils.iterate_extended_structure_values(sensor_ids)))

        config_placement = core_utils.zip3_extended_structures(
            entry_serial_numbers, sensor_ids, group_idxs
        )

        self.ampl_curves = core_utils.map_over_extended_structure(
            lambda args: self._create_amplitude_curves_for_subsweeps(
                args[0],
                *args[1],
                num_groups=len(session_config.groups),
                num_sensors=num_unique_sensors,
            ),
            core_utils.zip_extended_structures(session_config.groups, config_placement),
        )

        self.ampl_plot = self.amplitude_plot_widget.addPlot()
        self.ampl_plot.setMenuEnabled(False)
        self.ampl_plot.showGrid(x=True, y=True)
        self.ampl_plot.setLabel("left", "Amplitude")
        self.ampl_plot.setLabel("bottom", "Distance (m)")
        if (
            len(session_config.groups) > 1
            or num_unique_sensors > 1
            or any(
                sensor_config.num_subsweeps > 1
                for sensor_config in core_utils.iterate_extended_structure_values(
                    session_config.groups
                )
            )
        ):
            self.ampl_plot.addLegend(brush=SEMI_TRANSPARENT_BRUSH)

        for curves in core_utils.iterate_extended_structure_values(self.ampl_curves):
            for curve in curves:
                self.ampl_plot.addItem(curve)

    @staticmethod
    def _legend_label(
        sensor_id: int,
        group_idx: int,
        subsweep_index: int,
        num_groups: int,
        num_sensors: int,
        num_subsweeps: int,
    ) -> str:
        parts = []

        if num_groups > 1:
            if num_sensors > 1 or num_subsweeps > 1:
                parts += [f"G{group_idx}"]
            else:
                parts += [f"Group {group_idx}"]

        if num_sensors > 1:
            if num_groups > 1 or num_subsweeps > 1:
                parts += [f"S{sensor_id}"]
            else:
                parts += [f"Sensor {sensor_id}"]

        if num_subsweeps > 1:
            if num_groups > 1 or num_sensors > 1:
                parts += [f"SS{subsweep_index + 1}"]
            else:
                parts += [f"Subsweep {subsweep_index + 1}"]

        return ":".join(parts)

    def _create_amplitude_curves_for_subsweeps(
        self,
        sensor_config: a121.SensorConfig,
        entry_serial_number: int,
        sensor_id: int,
        group_idx: int,
        *,
        num_groups: int,
        num_sensors: int,
    ) -> list[pg.PlotDataItem]:
        subsweep_styles = [
            QtCore.Qt.PenStyle.SolidLine,
            QtCore.Qt.PenStyle.DashLine,
            QtCore.Qt.PenStyle.DotLine,
            QtCore.Qt.PenStyle.DashDotLine,
        ]

        return [
            pg.PlotDataItem(
                name=self._legend_label(
                    sensor_id,
                    group_idx,
                    index,
                    num_groups,
                    num_sensors,
                    sensor_config.num_subsweeps,
                ),
                pen=et.utils.pg_pen_cycler(entry_serial_number, style=subsweep_styles[index]),
            )
            for index, subsweep in enumerate(sensor_config.subsweeps)
        ]

    def _setup_phase_and_dvm(
        self, session_config: a121.SessionConfig, metadatas: list[dict[int, a121.Metadata]]
    ) -> None:
        phase_curves = []
        dvm_images = []

        for group_idx, sensor_id, sensor_config in core_utils.iterate_extended_structure(
            session_config.groups
        ):
            plot_widget = self.tab_widget.newPlotWidget(f"G{group_idx}:S{sensor_id}")

            phase_plot = plot_widget.addPlot(colspan=sensor_config.num_subsweeps)
            phase_plot.setMenuEnabled(False)
            phase_plot.showGrid(x=True, y=True)
            phase_plot.setLabel("left", "Phase")
            phase_plot.setYRange(-np.pi, np.pi)
            phase_plot.getAxis("left").setTicks(et.utils.pg_phase_ticks)

            if sensor_config.num_subsweeps > 1:
                phase_plot.addLegend(brush=SEMI_TRANSPARENT_BRUSH)

            subsweep_styles = [
                dict(symbol="o", symbolSize=5),  # circle
                dict(symbol="t1", symbolSize=5),  # triangle
                dict(symbol="s", symbolSize=4),  # square
                dict(symbol="d", symbolSize=6),  # diamond
            ]

            subsweep_phase_curves = [
                pg.PlotDataItem(
                    name=f"Subsweep {i + 1}",
                    pen=None,
                    **subsweep_styles[i],
                    symbolBrush=et.utils.pg_brush_cycler(0),
                    symbolPen="k",
                )
                for i in range(sensor_config.num_subsweeps)
            ]

            phase_curves.append((group_idx, sensor_id, subsweep_phase_curves))

            for phase_curve in subsweep_phase_curves:
                phase_plot.addItem(phase_curve)

            plot_widget.nextRow()

            subsweeps_distances_m = self.subsweeps_distances_m[group_idx][sensor_id]

            metadata = metadatas[group_idx][sensor_id]
            vels, vel_res = algo.get_approx_fft_vels(metadata, sensor_config)
            images = []
            for subsweep_index, subsweep_distances_m in enumerate(subsweeps_distances_m):
                step_length = sensor_config.subsweeps[subsweep_index].step_length
                plot = plot_widget.addPlot()
                plot.setMenuEnabled(False)
                plot.setLabel("bottom", "Distance (m)")
                plot.setLabel("left", "Velocity (m/s)")

                if sensor_config.num_subsweeps > 1:
                    plot.setTitle(f"Subsweep {subsweep_index + 1}")

                transform = QTransform()
                transform.translate(subsweep_distances_m[0], vels[0] - 0.5 * vel_res)
                transform.scale(metadata.base_step_length_m * step_length, vel_res)

                image = pg.ImageItem(autoDownsample=True)
                image.setLookupTable(et.utils.pg_mpl_cmap("viridis"))
                image.setTransform(transform)

                plot.addItem(image)
                images.append(image)

            dvm_images.append((group_idx, sensor_id, images))

        self.phase_curves = core_utils.create_extended_structure(phase_curves)
        self.ft_images = core_utils.create_extended_structure(dvm_images)


class PluginSpec(
    ProcessorPluginSpec[
        List[Dict[int, a121.Result]],
        ProcessorConfig,
        ProcessorResult,
        List[Dict[int, a121.Metadata]],
    ]
):
    def create_backend_plugin(
        self, callback: Callable[[Message], None], key: str
    ) -> BackendPlugin:
        return BackendPlugin(callback=callback, generation=self.generation, key=key)

    def create_view_plugin(self, app_model: AppModel) -> ViewPlugin:
        return ViewPlugin(app_model=app_model)

    def create_plot_plugin(self, app_model: AppModel) -> PlotPlugin:
        return PlotPlugin(app_model=app_model)


SPARSE_IQ_PLUGIN = PluginSpec(
    generation=PluginGeneration.A121,
    key="sparse_iq",
    title="Sparse IQ",
    description="Basic usage of the sparse IQ service.",
    family=PluginFamily.SERVICE,
    presets=[
        PluginPresetBase(name="Default", preset_id=PluginPresetId.DEFAULT),
    ],
    default_preset_id=PluginPresetId.DEFAULT,
)
