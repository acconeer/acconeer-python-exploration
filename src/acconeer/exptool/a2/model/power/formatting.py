# Copyright (c) Acconeer AB, 2026
# All rights reserved
"""Text formatting utilities for power model data."""

from __future__ import annotations

import collections

from . import domain
from .domain import CurrentBreakdown


_A_to_mA = _s_to_ms = 1000
_A_to_uA = _s_to_us = 1000000
_MU = "µ"
_VOLTAGE = 1.8

_TAG_NAMES = {
    domain.EnergyRegion.Tag.MEASURE: "Measure",
    domain.EnergyRegion.Tag.CALIBRATION: "Calibration",
    domain.EnergyRegion.Tag.IDLE: "Idle",
    domain.EnergyRegion.Tag.OVERHEAD: "Overhead",
    domain.EnergyRegion.Tag.PROCESSING: "Processing",
    domain.EnergyRegion.Tag.RS_INITIALIZATION: "RS Init",
    domain.EnergyRegion.Tag.APS_INITIALIZATION: "APS Init",
}

# Synthetic key written by the loader for non-split data. Hidden
# from breakdown rendering since it isn't a real named component.
_TOTAL_KEY = "total"


def format_current(current: float) -> str:
    if current > 1.0:
        return f"{current:.2f} A"
    elif current > 1.0e-3:
        return f"{current * _A_to_mA:.2f} mA"
    else:
        return f"{current * _A_to_uA:.0f} {_MU}A"


def format_duration(dur: float) -> str:
    if dur > 1.0:
        return f"{dur:.3f} s"
    elif dur > 1.0e-3:
        return f"{dur * _s_to_ms:.3f} ms"
    else:
        return f"{dur * _s_to_us:.1f} {_MU}s"


def format_energy(current: float, duration: float) -> str:
    energy_wh = current * duration * _VOLTAGE / 3600
    if energy_wh > 1e-3:
        return f"{energy_wh * 1e3:.2f} mWh"
    elif energy_wh > 1e-6:
        return f"{energy_wh * 1e6:.2f} {_MU}Wh"
    else:
        return f"{energy_wh * 1e9:.1f} nWh"


_BASE_COLUMNS: tuple[str, ...] = (
    "State",
    "Duration",
    "Avg Current",
    "Energy",
    "Share",
)


def _collect_components(profile: domain.CompositeRegion) -> tuple[str, ...]:
    """Return the component names that appear in the profile, sorted.

    The synthetic ``"total"`` placeholder written for non-split data is
    excluded — it carries the scalar total, not a real named component.
    """
    components: set[str] = set()
    for r in profile.flat_iter():
        if isinstance(r.current, CurrentBreakdown):
            components.update(r.current.currents)
    components.discard(_TOTAL_KEY)
    return tuple(sorted(components))


def profile_columns(
    profile: domain.CompositeRegion | None = None,
    show_components: bool = False,
) -> tuple[str, ...]:
    """Return the columns used by ``profile_rows`` for the given mode.

    When ``show_components`` is True, the component names are derived from
    ``profile`` (so they match the loaded YAML rather than a hardcoded
    enum). If ``profile`` is None the base columns are returned.
    """
    if not show_components or profile is None:
        return _BASE_COLUMNS
    return _BASE_COLUMNS + _collect_components(profile)


# Backwards-compatible alias for the no-breakdown column set.
PROFILE_COLUMNS: tuple[str, ...] = _BASE_COLUMNS


def profile_rows(
    profile: domain.CompositeRegion,
    show_components: bool = False,
) -> list[tuple[str, ...]]:
    """Return formatted rows for a power profile, one per non-empty tag.

    Each row matches ``profile_columns(profile, show_components)``. Useful
    for populating a Qt table or building an ASCII rendering.
    """
    tag_groups: dict[
        domain.EnergyRegion.Tag | None,
        list[domain.SimpleRegion],
    ] = collections.defaultdict(list)
    for region in profile.flat_iter():
        tag_groups[region.tag].append(region)

    total_energy = sum(r.average_current * r.duration for r in profile.flat_iter())

    components = _collect_components(profile) if show_components else ()

    rows: list[tuple[str, ...]] = []
    for tag in domain.EnergyRegion.Tag:
        regions = tag_groups.get(tag, [])
        if not regions:
            continue

        total_dur = sum(r.duration for r in regions)
        total_charge = sum(r.average_current * r.duration for r in regions)
        avg_current = total_charge / total_dur if total_dur > 0 else 0.0
        share = total_charge / total_energy * 100 if total_energy > 0 else 0.0

        cells: tuple[str, ...] = (
            _TAG_NAMES.get(tag, tag.name),
            format_duration(total_dur),
            format_current(avg_current),
            format_energy(avg_current, total_dur),
            f"{share:.1f}%",
        )

        if components:
            component_totals: dict[str, float] = {s: 0.0 for s in components}
            for region in regions:
                if isinstance(region.current, CurrentBreakdown):
                    bd = region.current
                    for component in components:
                        component_totals[component] += (
                            bd.currents.get(component, 0.0) * region.duration
                        )
            cells += tuple(
                format_current(component_totals[s] / total_dur if total_dur > 0 else 0.0)
                for s in components
            )

        rows.append(cells)

    return rows


def render_profile(
    profile: domain.CompositeRegion,
    show_components: bool = False,
) -> list[str]:
    """Render a power profile as a list of monospaced text lines."""
    columns = profile_columns(profile, show_components)
    widths = [22, 12, 12, 12, 7] + [10] * (len(columns) - len(_BASE_COLUMNS))
    aligns = ["<", ">", ">", ">", ">"] + [">"] * (len(columns) - len(_BASE_COLUMNS))
    header = " ".join(f"{c:{a}{w}}" for c, w, a in zip(columns, widths, aligns))
    lines = [header, "-" * len(header)]
    for row in profile_rows(profile, show_components):
        lines.append(" ".join(f"{v:{a}{w}}" for v, w, a in zip(row, widths, aligns)))
    return lines
