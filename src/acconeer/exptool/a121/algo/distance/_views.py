# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import copy
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Optional, overload

import attrs
import numpy as np
import numpy.typing as npt

from acconeer.exptool import a121


@dataclass(frozen=True)
class SubsweepSlices(Sequence[slice]):
    """
    Container holding different reference views of subsweep slices.

    The subsweep segmentation is defined consistently, but can be
    interpreted in different sweep domains:

    - full sweep: raw subsweep slices over the full sweep signal
    - valid sweep: subsweep slices restricted to valid (unmasked) samples
    - cropped sweep: subsweep slices expressed in a cropped sweep domain

    Conceptual illustration:

        full sweep:
            [[........][.........][.........]]

        valid sweep (mask applied, margin = 2):
            [..[......][.........][.......]..]

        cropped sweep:
              [[......][.........][.......]]
    """

    full: list[slice]

    @overload
    def __getitem__(self, index: int) -> slice: ...

    @overload
    def __getitem__(self, index: slice) -> list[slice]: ...

    def __getitem__(self, index: int | slice) -> slice | list[slice]:
        return self.full[index]

    def __iter__(self) -> Iterator[slice]:
        return iter(self.full)

    def __len__(self) -> int:
        return len(self.full)

    @property
    def _num_points(self) -> int:
        """Total number of points in the full sweep defined by the subsweep slices."""
        if not self.full:
            return 0

        last_slice = self.full[-1]
        return int(last_slice.stop) - int(self.full[0].start)

    def valid(self, edge_margin: int = 0) -> list[slice]:
        """
        Subsweep slices restricted to valid samples (e.g. after filtering) of the full sweep.

        Args:
            edge_margin:
                Number of samples to ignore on both sides of the range sweep.

        Returns:
            List of slices, one per subsweep.
        """
        if edge_margin < 0:
            msg = "edge_margin must be >= 0."
            raise ValueError(msg)

        total_points = self._num_points

        if 2 * edge_margin > total_points:
            msg = f"edge_margin={edge_margin} too large for total_points={total_points}."
            raise ValueError(msg)

        valid_slices = copy.deepcopy(self.full)
        valid_slices[0] = slice(
            valid_slices[0].start + edge_margin,
            valid_slices[0].stop,
            valid_slices[0].step,
        )
        valid_slices[-1] = slice(
            valid_slices[-1].start,
            valid_slices[-1].stop - edge_margin,
            valid_slices[-1].step,
        )

        return valid_slices

    def cropped(self, edge_margin: int = 0) -> list[slice]:
        """
        Subsweep slices expressed in the cropped sweep domain (e.g. after filtering).

        Args:
            edge_margin:
                Number of samples cropped on both sides of the range sweep.

        Returns:
            List of slices, one per subsweep.
        """
        # Crop the full slices by the specified edge margin and adjust to cropped domain
        cropped_slices = [
            slice(
                s.start - edge_margin,
                s.stop - edge_margin,
                s.step,
            )
            for s in self.valid(edge_margin=edge_margin)
        ]

        return cropped_slices


@attrs.frozen(kw_only=True, slots=True)
class RangeSweepConfig:
    """
    View on a selected set of subsweeps that together form one contiguous range sweep.

    All subsweeps must have phase enhancement enabled, the same profile and step_length and must be contiguous in distance points,
    i.e. the next subsweep must start where the previous one ends.
    """

    subsweep_configs: list[a121.SubsweepConfig] = attrs.field(  # type: ignore[var-annotated]
        converter=lambda configs: sorted(configs, key=lambda config: config.start_point)
    )

    def __attrs_post_init__(self) -> None:
        if not self.subsweep_configs:
            msg = "subsweep_configs must not be empty."
            raise ValueError(msg)

        self._validate_phase_enhancement_enabled()
        self._validate_uniform_profile()
        self._validate_uniform_step_length()
        self._validate_contiguous_layout()

    @classmethod
    def from_sensor_config(
        cls,
        sensor_config: a121.SensorConfig,
        subsweep_indexes: Optional[Sequence[int]] = None,
    ) -> RangeSweepConfig:
        """
        Build a RangeSweepConfig from a sensor config.

        If `subsweep_indexes` is None, all subsweeps are used.
        """
        if subsweep_indexes is None:
            selected_subsweep_configs = sensor_config.subsweeps
        else:
            selected_subsweep_configs = [
                sensor_config.subsweeps[index] for index in subsweep_indexes
            ]

        return cls(subsweep_configs=selected_subsweep_configs)

    def _validate_contiguous_layout(self) -> None:
        next_expected_start_point = self.start_point
        for subsweep_config in self.subsweep_configs:
            if subsweep_config.start_point != next_expected_start_point:
                msg = "Subsweeps used for range processing must be contiguous."
                raise ValueError(msg)

            next_expected_start_point = (
                subsweep_config.start_point + subsweep_config.num_points * self.step_length
            )

    def _validate_phase_enhancement_enabled(self) -> None:
        for subsweep_config in self.subsweep_configs:
            if not subsweep_config.phase_enhancement:
                msg = "Phase enhancement must be enabled in subsweep configurations used for range processing."
                raise ValueError(msg)

    def _validate_uniform_profile(self) -> None:
        profiles = {subsweep_config.profile for subsweep_config in self.subsweep_configs}
        if len(profiles) != 1:
            msg = f"Expected same profile for all subsweeps, got {profiles}"
            raise ValueError(msg)

    def _validate_uniform_step_length(self) -> None:
        step_lengths = {subsweep_config.step_length for subsweep_config in self.subsweep_configs}
        if len(step_lengths) != 1:
            msg = f"Expected same step length for all subsweeps, got {step_lengths}"
            raise ValueError(msg)

    @property
    def num_subsweeps(self) -> int:
        """Number of subsweeps in this range sweep."""
        return len(self.subsweep_configs)

    @property
    def profile(self) -> a121.Profile:
        (profile,) = {subsweep_config.profile for subsweep_config in self.subsweep_configs}
        return profile

    @property
    def start_point(self) -> int:
        return self.subsweep_configs[0].start_point

    @property
    def start_points(self) -> list[int]:
        return [subsweep_config.start_point for subsweep_config in self.subsweep_configs]

    @property
    def num_points(self) -> int:
        return sum(subsweep_config.num_points for subsweep_config in self.subsweep_configs)

    @property
    def step_length(self) -> int:
        (step_length,) = {subsweep_config.step_length for subsweep_config in self.subsweep_configs}
        return step_length

    @property
    def distance_points(self) -> npt.NDArray[np.intp]:
        return self.start_point + np.arange(self.num_points) * self.step_length

    @property
    def hwaas_per_subsweep(self) -> list[int]:
        return [subsweep_config.hwaas for subsweep_config in self.subsweep_configs]

    @property
    def subsweep_slices(self) -> SubsweepSlices:
        """
        Return slices into the full flattened range sweep for each subsweep.

        Returns:
            SubsweepSlices object containing slices for each subsweep.
        """
        slices: list[slice] = []
        offset = 0

        for subsweep_config in self.subsweep_configs:
            subsweep_start = offset
            subsweep_stop = offset + subsweep_config.num_points

            slices.append(slice(subsweep_start, subsweep_stop, 1))

            offset += subsweep_config.num_points

        return SubsweepSlices(slices)
