# Copyright (c) Acconeer AB, 2023-2026
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

These are called composite regions.

P.S. Composite regions can be composed from other composite regions.
"""

from __future__ import annotations

import collections.abc
import functools
import itertools
import operator
import types
import typing as t
from enum import Enum, auto

import attrs
import typing_extensions as te


_T = t.TypeVar("_T")


def _freeze_currents(c: t.Mapping[str, float]) -> t.Mapping[str, float]:
    # Wrap the input in a read-only mapping so the dict stored on the
    # frozen CurrentBreakdown can't be mutated after construction
    # (which would otherwise corrupt cached hashes on
    # SimpleRegion(cache_hash=True)).
    return types.MappingProxyType({k: float(v) for k, v in c.items()})


def _currents_eq_key(c: t.Mapping[str, float]) -> tuple[tuple[str, float], ...]:
    # Transform Mapping into a hashable tuple so CurrentBreakdown
    # (and therefore SimpleRegion(cache_hash=True)) can be used as
    # @functools.cache keys.
    return tuple(sorted(c.items()))


@attrs.frozen
class CurrentBreakdown:
    """A region's current broken down by named components.

    Keys are arbitrary strings (defined by the loader / YAML file). The
    domain layer doesn't know the key set; it just carries whatever the
    loader hands it.
    """

    currents: t.Mapping[str, float] = attrs.field(
        converter=_freeze_currents,
        eq=_currents_eq_key,
    )

    @property
    def total(self) -> float:
        return sum(self.currents.values(), 0.0)

    @classmethod
    def zero(cls) -> CurrentBreakdown:
        # Empty breakdown; arithmetic uses union-of-keys, so this is the
        # identity element for both ``+`` and ``-``.
        return cls({})

    def __add__(self, other: CurrentBreakdown) -> CurrentBreakdown:
        keys = sorted(set(self.currents) | set(other.currents))
        return CurrentBreakdown(
            {s: self.currents.get(s, 0.0) + other.currents.get(s, 0.0) for s in keys}
        )

    def __sub__(self, other: CurrentBreakdown) -> CurrentBreakdown:
        keys = sorted(set(self.currents) | set(other.currents))
        return CurrentBreakdown(
            {s: self.currents.get(s, 0.0) - other.currents.get(s, 0.0) for s in keys}
        )


class EnergyRegion(collections.abc.Hashable, te.Protocol):
    """
    Interface of energy regions
    """

    class Tag(Enum):
        MEASURE = auto()
        CALIBRATION = auto()
        IDLE = auto()
        OVERHEAD = auto()
        PROCESSING = auto()
        RS_INITIALIZATION = auto()
        APS_INITIALIZATION = auto()

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


@attrs.frozen(cache_hash=True)
class SimpleRegion(EnergyRegion):
    """A simple region.

    ``current`` is either a scalar average current in amps or a
    :class:`CurrentBreakdown` recording the same current split into
    named components. ``average_current`` returns a scalar in both
    cases, so callers that only need the total don't have to care
    which shape is stored.
    """

    current: float | CurrentBreakdown
    duration: float = attrs.field(validator=attrs.validators.ge(0.0))
    tag: EnergyRegion.Tag | None = None
    description: str = ""

    @property
    def average_current(self) -> float:
        if isinstance(self.current, CurrentBreakdown):
            return self.current.total
        return self.current

    def truncate(self, new_duration: float) -> SimpleRegion:
        return attrs.evolve(
            self,
            duration=new_duration,
            description=f"{self.description} (truncated)",
        )


@attrs.frozen(cache_hash=True)
class CompositeRegion(EnergyRegion):
    """
    Composes energy regions in a tree-structure.
    """

    regions: tuple[EnergyRegion, ...]
    description: str = ""

    @property
    def average_current(self) -> float:
        return average_current(*self.regions)

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


@functools.cache
def duration(*regions: EnergyRegion) -> float:
    """
    Returns the total duration of a variable amount of regions
    """
    return sum(r.duration for r in regions)


@functools.cache
def average_current(*regions: EnergyRegion) -> float:
    """
    Returns the average current of a variable amount of regions
    """
    dur = duration(*regions)
    return sum(r.average_current * r.duration / dur for r in regions)


def _join(joiner: _T, iterable: t.Iterable[_T]) -> t.Iterator[_T]:
    """
    Similar to str.join (except the last concat step) but for any type.
    """
    iterator = iter(iterable)
    yield next(iterator)

    for e in iterator:
        yield joiner
        yield e
