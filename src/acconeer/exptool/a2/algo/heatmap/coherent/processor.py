# Copyright (c) Acconeer AB, 2024-2026
# All rights reserved

from __future__ import annotations

import copy

import attrs
import numpy as np
import numpy.typing as npt

from acconeer.exptool import a2
from acconeer.exptool.a2.algo._utils import tc_to_sf
from acconeer.exptool.a2.algo.heatmap.coherent.plot_config import CoherentHeatmapPlotConfig
from acconeer.exptool.a2.algo.heatmap.processor_common import (
    HeatmapProcessorCommon,
    ProcessorResultCommon,
)
from acconeer.exptool.a2.algo.nodes._beamforming_nodes import DelayAndSumBeamformNode
from acconeer.exptool.a2.algo.nodes._filter_nodes import DelayedExponentialHighPassNode
from acconeer.exptool.a2.algo.nodes._node import Node
from acconeer.exptool.a2.algo.nodes._simple_nodes import (
    MeanNode,
    ModeSelectNode,
    NoopNode,
    ReshapeNode,
)

from .config import HeatmapConfig


@attrs.frozen(kw_only=True)
class ProcessorResult(ProcessorResultCommon):
    heatmap_coherent: npt.NDArray[np.complex128] | None
    """Complex heatmap data."""


class HeatmapProcessor(HeatmapProcessorCommon[HeatmapConfig]):
    def __init__(
        self,
        subsweep_config: a2.SubsweepConfig,
        heatmap_config: HeatmapConfig,
        update_rate: float,
        display_mode: CoherentHeatmapPlotConfig.DisplayMode = CoherentHeatmapPlotConfig.DisplayMode.ANGLE,
    ) -> None:
        self.subsweep_config: a2.SubsweepConfig = subsweep_config
        self.heatmap_config: HeatmapConfig = heatmap_config

        self.mean_node = MeanNode[np.complex128](axis=0)
        self.movement_node: Node[npt.NDArray[np.complex128]]
        if self.heatmap_config.heatmap_mode == HeatmapConfig.HeatmapMode.MOVEMENT:
            movement_input_shape = (
                self.subsweep_config.num_points * self.subsweep_config.num_channels,
            )
            self.movement_node = DelayedExponentialHighPassNode[np.complex128](
                input_shape=movement_input_shape,
                lp_constant=np.float64(
                    tc_to_sf(heatmap_config.high_pass_filter_time_constant_s, update_rate)
                ),
                dtype=np.complex128,
            )
        else:
            self.movement_node = NoopNode[np.complex128]()

        target_shape = (self.subsweep_config.num_points, self.subsweep_config.num_channels)
        self.reshape_node = ReshapeNode[np.complex128](target_shape=target_shape)

        steering_vectors = self.heatmap_config.antenna_array.get_steering_vectors(
            self.heatmap_config.az_angles,
            self.heatmap_config.el_angles,
            self.subsweep_config.tx_antenna_mask,
            self.subsweep_config.rx_antenna_mask,
            profile=self.subsweep_config.profile,
        )

        self.coherent_beamformer = DelayAndSumBeamformNode(steering_vectors=steering_vectors)

        if display_mode == CoherentHeatmapPlotConfig.DisplayMode.ABSOLUTE:
            self.mode_selector = ModeSelectNode(mode="abs")
        else:
            self.mode_selector = ModeSelectNode(mode="angle")

    def process(self, result: a2.Result) -> ProcessorResult:
        """Process a SparseIQ Result

        Initializes internal state the first ``num_channels`` frames, then
        returns a heatmap every ``update_count`` frames.
        """
        mean_sweep: npt.NDArray[np.complex128] = self.mean_node.execute(result.frame)  # type: ignore[assignment]
        movement = self.movement_node.execute(mean_sweep)
        reshaped_frame = self.reshape_node.execute(movement)
        heatmap_coherent = self.coherent_beamformer.execute(reshaped_frame)
        heatmap: npt.NDArray[np.float64] = self.mode_selector.execute(heatmap_coherent)  # type: ignore[assignment]

        return ProcessorResult(
            heatmap=heatmap,
            heatmap_coherent=heatmap_coherent,
            heatmap_config=copy.copy(self.heatmap_config),
        )
