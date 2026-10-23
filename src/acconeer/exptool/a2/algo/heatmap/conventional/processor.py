# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved

from __future__ import annotations

import copy

import numpy as np
import numpy.typing as npt

from acconeer.exptool import a2
from acconeer.exptool.a2.algo._utils import tc_to_sf
from acconeer.exptool.a2.algo.heatmap.processor_common import (
    HeatmapProcessorCommon,
    ProcessorResultCommon,
)
from acconeer.exptool.a2.algo.nodes._beamforming_nodes import ConventionalBeamformNode
from acconeer.exptool.a2.algo.nodes._filter_nodes import (
    DelayedExponentialHighPassNode,
    ExponentialLowPassNode,
)
from acconeer.exptool.a2.algo.nodes._node import Node
from acconeer.exptool.a2.algo.nodes._simple_nodes import (
    CovarianceNode,
    MeanNode,
    NoopNode,
    ReshapeNode,
)

from .config import HeatmapConfig


ProcessorResult = ProcessorResultCommon


class HeatmapProcessor(HeatmapProcessorCommon[HeatmapConfig]):
    def __init__(
        self,
        subsweep_config: a2.SubsweepConfig,
        heatmap_config: HeatmapConfig,
        update_rate: float,
    ) -> None:
        self.subsweep_config: a2.SubsweepConfig = subsweep_config
        self.heatmap_config: HeatmapConfig = heatmap_config

        self.mean_node: MeanNode[np.complex128] = MeanNode(axis=0)

        movement_input_shape = (
            self.subsweep_config.num_points * self.subsweep_config.num_channels,
        )

        self.movement_node: Node[npt.NDArray[np.complex128]]

        if self.heatmap_config.heatmap_mode == HeatmapConfig.HeatmapMode.MOVEMENT:
            self.movement_node = DelayedExponentialHighPassNode[np.complex128](
                input_shape=movement_input_shape,
                lp_constant=np.float64(
                    tc_to_sf(heatmap_config.high_pass_filter_time_constant_s, update_rate)
                ),
                dtype=np.complex128,
            )
        else:
            self.movement_node = NoopNode[np.complex128]()

        self.update_rate = update_rate

        target_shape = (self.subsweep_config.num_points, self.subsweep_config.num_channels)
        self.reshape_node = ReshapeNode[np.complex128](target_shape=target_shape)
        self.covariance_node = CovarianceNode(axis=1)

        filter_input_shape = (
            self.subsweep_config.num_points,
            self.subsweep_config.num_channels,
            self.subsweep_config.num_channels,
        )
        self.filter_node = ExponentialLowPassNode(
            input_shape=filter_input_shape,
            lp_constant=np.float64(
                tc_to_sf(heatmap_config.covariance_matrix_time_constant_s, update_rate)
            ),
            dtype=np.complex128,
        )
        steering_vectors = self.heatmap_config.antenna_array.get_steering_vectors(
            self.heatmap_config.az_angles,
            self.heatmap_config.el_angles,
            self.subsweep_config.tx_antenna_mask,
            self.subsweep_config.rx_antenna_mask,
            profile=self.subsweep_config.profile,
        )

        self.conventional_beamformer = ConventionalBeamformNode(steering_vectors=steering_vectors)

    def process(self, result: a2.Result) -> ProcessorResult:
        """Process a SparseIQ Result

        Initializes internal state the first ``num_channels`` frames.
        """

        mean_sweep: npt.NDArray[np.complex128] = self.mean_node.execute(result.frame)  # type: ignore[assignment]

        movement = self.movement_node.execute(mean_sweep)

        reshaped_frame = self.reshape_node.execute(movement)

        cov_data = self.covariance_node.execute(reshaped_frame)

        fcov_data = self.filter_node.execute(cov_data)

        heatmap = self.conventional_beamformer.execute(fcov_data)

        return ProcessorResult(
            heatmap=heatmap,
            heatmap_config=copy.copy(self.heatmap_config),
        )
