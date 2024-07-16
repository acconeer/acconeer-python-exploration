# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved
r"""
This module contains the power modelling building blocks.

The main idea is that an energy region has a duration (seconds)
and an average current (ampere). This means that all energy regions
can be plotted on a 2d plot.

    A
    ^
    |
    |   +---------------+  \
    |   |               |   \_Average current
    |   | energy region |   /
    |   |               |  /
    +-------------------------> t

        |-- duration  --|

A rectangle like this is called a simple region.

In order to get more advanced regions, the simple regions
can be composed:

    A
    ^
    |         +-+
    |         | |
    |         |s|
    |         |r|-----+ ____Average current
    |   +-----|2| sr3 |
    |   | sr1 | |     |
    +-------------------------> t

        |seq. duration|

These are called composte regions.

P.S. Composite regions can be composed from other composite regions.
"""

from __future__ import annotations

import itertools
import operator
import typing as t
from enum import Enum, auto

import attrs
import typing_extensions as te


_T = t.TypeVar("_T")


class EnergyRegion(te.Protocol):
    """
    Interface of energy regions
    """

    class Tag(Enum):
        MEASURE = auto()
        CALIBRATION = auto()
        IDLE = auto()
        OVERHEAD = auto()
        PROCESSING = auto()
        COMMUNICATION = auto()

    @property
    def average_current(self) -> float: ...

    @property
    def duration(self) -> float: ...

    @property
    def charge(self) -> float:
        return self.average_current * self.duration

    @property
    def description(self) -> str: ...

    def truncate(self, new_duration: float) -> EnergyRegion:
        """Returns a (time-)truncated copy of this region"""
        ...

    def join(self, regions: t.Iterable[EnergyRegion], description: str = "") -> EnergyRegion:
        """
        Helper function. See `_join`
        """
        regions = tuple(regions)

        if len(regions) == 0:
            msg = "Cannot join an empty sequence."
            raise ValueError(msg)
        elif len(regions) == 1:
            (region,) = regions
            return region
        else:
            return CompositeRegion(tuple(_join(self, regions)), description)


@attrs.frozen
class SimpleRegion(EnergyRegion):
    """A simple region"""

    current: float
    duration: float = attrs.field(validator=attrs.validators.ge(0.0))
    tag: t.Optional[EnergyRegion.Tag] = None
    description: str = ""

    @property
    def average_current(self) -> float:
        return self.current

    def truncate(self, new_duration: float) -> SimpleRegion:
        return attrs.evolve(
            self,
            duration=new_duration,
            description=f"{self.description} (truncated)",
        )


@attrs.frozen
class CompositeRegion(EnergyRegion):
    """
    Composes energy regions in a tree-structure.
    """

    regions: tuple[EnergyRegion, ...]
    description: str = ""

    @property
    def average_current(self) -> float:
        return sum(r.average_current * r.duration / self.duration for r in self.regions)

    @property
    def duration(self) -> float:
        return duration(*self.regions)

    def truncate(self, new_duration: float) -> CompositeRegion:
        durations = (r.duration for r in self.regions)
        starts = itertools.accumulate(durations, operator.add)
        index_to_truncate = sum(start < new_duration for start in starts)

        whole_regions = self.regions[:index_to_truncate]
        whole_regions_duration = sum(r.duration for r in whole_regions)
        if index_to_truncate < len(self.regions):
            truncated_region = self.regions[index_to_truncate].truncate(
                new_duration - whole_regions_duration
            )
            return CompositeRegion(
                whole_regions + (truncated_region,), description=self.description
            )
        else:
            return CompositeRegion(whole_regions, description=self.description)

    def flat_iter(self) -> t.Iterator[SimpleRegion]:
        """
        Returns an in-order iterator of all the SimpleRegions (leaf nodes).
        """
        for r in self.regions:
            if isinstance(r, SimpleRegion):
                yield r
            elif isinstance(r, CompositeRegion):
                yield from r.flat_iter()


def duration(*regions: EnergyRegion) -> float:
    """
    Returns the total duration of a variable amount of regions
    """
    return sum(r.duration for r in regions)


def _join(joiner: _T, iterable: t.Iterable[_T]) -> t.Iterator[_T]:
    """
    Similar to str.join (except the last concat step) but for any type.
    """
    iterator = iter(iterable)
    yield next(iterator)

    for e in iterator:
        yield joiner
        yield e
