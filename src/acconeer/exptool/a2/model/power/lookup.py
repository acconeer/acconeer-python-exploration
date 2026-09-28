# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved

from __future__ import annotations

import collections
import functools
import importlib.resources
import typing as t
from enum import Enum, auto
from pathlib import Path

import attrs
import typing_extensions as te
import yaml

from acconeer.exptool import a2

from .domain import CurrentBreakdown, SimpleRegion


def _packaged_data_path() -> Path:
    # Use importlib.resources so the YAML is found whether the package is
    # imported from a source checkout or installed as a wheel.
    return Path(str(importlib.resources.files(__package__).joinpath("lookup.yaml")))


_DATA_PATH = _packaged_data_path()

# Reserved key inside a per-region current dict that holds a non-split
# total (used by both the YAML ``{total: X}`` shorthand and the loader's
# scalar code path). Kept distinct from component names so we can detect
# the format from the value alone.
_TOTAL_KEY = "total"
_MODEL_KEYS = frozenset({"intercept", "slope_per_mhz"})


@attrs.frozen
class Sensor:
    """A reference to a sensor variant; carries the temperature lookup key.

    Used by the API as an opaque, hashable token. ``Sensor()`` selects the
    default temperature; ``Sensor.at_temperature(value)`` picks an explicit
    one (the ``value`` must exist in the YAML's ``temperatures`` section).
    """

    temperature: int = 25

    def get_sensor_data(self) -> SensorConstants:
        return SensorConstants.at_temperature(self.temperature)

    @classmethod
    def at_temperature(cls, temperature: int) -> Sensor:
        return cls(temperature=temperature)


DEFAULT_SENSOR: Sensor = Sensor()


def _bd(total: float) -> CurrentBreakdown:
    """Wrap a scalar total in a single-key breakdown.

    Used for non-split YAML data. The synthetic ``"total"`` key keeps the
    total accessible via ``.total`` and via the loader's reference-resolution
    path, while making it clear that no broken-down data is present.
    """
    return CurrentBreakdown({_TOTAL_KEY: float(total)})


def _is_breakdown_dict(d: t.Mapping[str, t.Any]) -> bool:
    """Return True if the dict carries component keys (anything but total)."""
    return any(k != _TOTAL_KEY for k in d)


def _scb_from_value(v: t.Any) -> CurrentBreakdown:
    """Build a CurrentBreakdown from a YAML value.

    Accepts one of (mutually exclusive):
    - broken-down dict ``{io: ..., dig: ..., ...}``  (split format)
    - scalar (int/float)                            (non-split format)
    - ``{total: X}`` dict                           (non-split, explicit)

    Mixing a broken-down dict with a ``total`` key is rejected; otherwise
    the loader would silently drop one of them.
    """
    if isinstance(v, (int, float)):
        return _bd(float(v))
    if isinstance(v, dict):
        has_total = _TOTAL_KEY in v
        has_components = _is_breakdown_dict(v)
        if has_total and has_components:
            msg = f"Current value cannot mix 'total' with component keys: {v!r}"
            raise ValueError(msg)
        if has_total:
            return _bd(float(v[_TOTAL_KEY]))
        if has_components:
            return CurrentBreakdown({k: float(val) for k, val in v.items()})
    msg = f"Cannot parse current value: {v!r}"
    raise ValueError(msg)


_MODEL_PAIR_MSG = "Measure model entry must have exactly 'intercept' and 'slope_per_mhz'"


def _model_coeffs(v: t.Any) -> tuple[float, float]:
    if not isinstance(v, dict) or set(v) != _MODEL_KEYS:
        msg = f"{_MODEL_PAIR_MSG}: {v!r}"
        raise ValueError(msg)
    return float(v["intercept"]), float(v["slope_per_mhz"])


def _load_measure_model(
    d: t.Mapping[int, t.Any],
) -> dict[a2.Profile, dict[str, tuple[float, float]]]:
    """Load the per-profile measure model, keyed by component.

    The profiles have to carry the same components, or the ones carrying
    fewer would be subtracted into negative ones.
    """
    model = {}
    for k, v in d.items():
        if not isinstance(v, dict) or not v:
            msg = f"Measure model entry must be a coefficient pair or a mapping of them: {v!r}"
            raise ValueError(msg)
        if set(v) == _MODEL_KEYS:
            model[a2.Profile(k)] = {_TOTAL_KEY: _model_coeffs(v)}
            continue
        if _MODEL_KEYS & set(v):
            msg = f"{_MODEL_PAIR_MSG}: {v!r}"
            raise ValueError(msg)
        if _TOTAL_KEY in v:
            msg = f"Measure model entry cannot mix 'total' with component keys: {v!r}"
            raise ValueError(msg)
        model[a2.Profile(k)] = {
            str(component): _model_coeffs(coeffs) for component, coeffs in v.items()
        }
    shapes = {frozenset(coeffs) for coeffs in model.values()}
    if len(shapes) > 1:
        msg = (
            f"Measure model profiles must carry the same components: {sorted(map(sorted, shapes))}"
        )
        raise ValueError(msg)
    return model


def _load_transition(
    d: dict[str, t.Any],
    aps_active: t.Mapping[str, CurrentBreakdown] | None = None,
) -> SimpleRegion:
    """Load a SimpleRegion from YAML.

    The transition is expressed as either ``{current: <value>, duration: ...}``
    or ``{total: <scalar>, duration: ...}`` — but not both. ``current``
    may be a broken-down dict, a scalar, or a string reference into
    ``aps_active``.
    """
    duration = d["duration"]
    has_total = _TOTAL_KEY in d
    has_current = "current" in d
    if has_total and has_current:
        msg = f"State transition cannot have both 'total' and 'current': {d!r}"
        raise ValueError(msg)
    if has_current:
        current = d["current"]
        if isinstance(current, str) and aps_active is not None:
            return SimpleRegion(current=aps_active[current], duration=duration)
        return SimpleRegion(current=_scb_from_value(current), duration=duration)
    if has_total:
        return SimpleRegion(current=_bd(d[_TOTAL_KEY]), duration=duration)
    msg = f"State transition missing 'current' or 'total': {d!r}"
    raise ValueError(msg)


_CURRENT_SECTIONS = (
    "sleep_currents",
    "aps_idle_currents",
    "idle_currents",
    "aps_active_currents",
)


def _named_currents(d: dict[str, t.Any]) -> t.Iterator[tuple[str, t.Any]]:
    """Yield every current the derived currents are built from."""
    for section in _CURRENT_SECTIONS:
        for name, value in (d.get(section) or {}).items():
            yield f"{section}.{name}", value
    # Subtracted from the measure current in turn, one nesting level deeper.
    for profile, channels in (d.get("rx_antenna_current") or {}).items():
        for channel, value in (channels or {}).items():
            yield f"rx_antenna_current.{profile}.{channel}", value


def _detect_current_breakdown(d: dict[str, t.Any]) -> bool:
    """Probe the YAML to decide whether broken-down data is present.

    Every current has to agree: the derived ones subtract one from another,
    so a half-split file grows a stray total that the breakdown view drops
    rather than plots.
    """
    split = {
        name: isinstance(value, dict) and _is_breakdown_dict(value)
        for name, value in _named_currents(d)
    }
    if len(set(split.values())) > 1:
        totals = sorted(name for name, is_split in split.items() if not is_split)
        rest = f", and {len(totals) - 4} more" if len(totals) > 4 else ""
        shown = ", ".join(totals[:4]) + rest
        msg = f"Every current must agree on being split; these are totals: {shown}"
        raise ValueError(msg)
    return any(split.values())


@attrs.frozen
class SensorConstants:
    """
    Representation of a sensor.

    Consists of multiple table for different currents, overhead-
    and transition times.
    """

    class ApsSleepState(Enum):
        APS_HF_WFI = auto()
        APS_MF_WFI = auto()
        APS_LF_WFI = auto()
        SHALLOW_SLEEP = auto()
        DEEP_SLEEP = auto()
        ULTRA_DEEP_SLEEP = auto()

    class ApsIdleState(Enum):
        APS_HF_WFI = auto()
        APS_MF_WFI = auto()
        APS_LF_WFI = auto()

    class ApsActiveState(Enum):
        APS_HF = auto()
        APS_MF = auto()
        APS_LF = auto()

    class RsIdleState(Enum):
        RS_OFF = auto()
        RS_READY_WFI = auto()
        RS_ARMED_WFI = auto()

    idle_currents: t.Mapping[a2.IdleState, CurrentBreakdown]
    inter_sweep_currents: t.Mapping[a2.IdleState, CurrentBreakdown]
    inter_sweep_currents_hsm: t.Mapping[a2.IdleState, CurrentBreakdown]
    inter_frame_rs_currents: t.Mapping[a2.IdleState, CurrentBreakdown]
    inter_frame_aps_currents: t.Mapping[ApsSleepState | ApsIdleState, CurrentBreakdown]
    aps_active_currents: t.Mapping[ApsActiveState, CurrentBreakdown]
    aps_sleep_wakeup_state: t.Mapping[ApsSleepState, SimpleRegion]
    aps_go_to_sleep_state: t.Mapping[ApsSleepState, SimpleRegion]
    measure_currents: t.Mapping[a2.Profile, t.Mapping[a2.PRF, CurrentBreakdown]]
    rx_antenna_current: t.Mapping[a2.Profile, t.Mapping[int, CurrentBreakdown]]

    frame_overhead: float
    frame_overhead_hsm: float
    sweep_setup_times: t.Mapping[a2.IdleState, float]
    subsweep_setup_times_hsm: t.Mapping[a2.IdleState, float]
    subsweep_setup_time: float
    subsweep_setup_time_loopback: float

    calibration_state: SimpleRegion
    radar_prepare_state: SimpleRegion
    radar_prepare_rs_init_state: SimpleRegion
    radar_power_on_state: SimpleRegion
    radar_power_off_state: SimpleRegion
    aps_lf_to_hf_state: SimpleRegion
    aps_mf_to_hf_state: SimpleRegion
    aps_hf_to_lf_state: SimpleRegion
    aps_hf_to_mf_state: SimpleRegion

    sample_durations: t.Mapping[a2.Profile, t.Mapping[a2.PRF, float]]
    jitter_compensation_duration: float

    iq_processing_fixed: float
    iq_processing_per_point: float

    capon_processing_per_param: float
    capon_update_per_point: float
    coherent_processing_per_param: float
    coherent_update_per_point: float
    conventional_processing_per_param: float
    conventional_update_per_point: float
    robust_capon_processing_per_param: float
    robust_capon_update_per_point: float

    # True when the loaded YAML carries per-component current breakdowns.
    # UI surfaces that depend on broken-down data should hide when it is False.
    has_current_breakdown: bool = False

    # Temperatures available in the YAML (sorted, °C). Empty when the
    # file has no ``temperatures`` section, i.e. only the base values
    # are usable.
    available_temperatures: tuple[int, ...] = ()

    @classmethod
    @functools.cache
    def at_temperature(
        cls,
        temperature: int,
        path: str | Path = _DATA_PATH,
    ) -> te.Self:
        """Returns sensor lookup tables for the given temperature (cached).

        The ``(cls, temperature, path)`` tuple is the cache key, so each
        ``(SensorConstants subclass, temperature, file)`` combination is
        parsed at most once. ``Path`` and ``str`` keys for the same file
        are treated as distinct.
        """
        return cls.from_yaml(path, temperature)

    @classmethod
    def none(cls) -> te.Self:
        return attrs.evolve(
            cls.default(),
            inter_sweep_currents=collections.defaultdict(CurrentBreakdown.zero),
            inter_sweep_currents_hsm=collections.defaultdict(CurrentBreakdown.zero),
            inter_frame_rs_currents=collections.defaultdict(CurrentBreakdown.zero),
            inter_frame_aps_currents=collections.defaultdict(CurrentBreakdown.zero),
            measure_currents=collections.defaultdict(
                lambda: collections.defaultdict(CurrentBreakdown.zero)
            ),
        )

    @classmethod
    def from_yaml(
        cls,
        path: str | Path = _DATA_PATH,
        temperature: int = 25,
    ) -> te.Self:
        """Load sensor data from a YAML file.

        Temperature-specific values under ``"temperatures"`` are merged on
        top of the top-level constants. If a non-default temperature is
        requested but the file has no entry for it, this raises rather
        than silently returning the base data.
        """
        with open(path, encoding="utf-8") as f:
            d = yaml.safe_load(f)
        temperatures = d.get("temperatures", {})
        if temperatures:
            if temperature not in temperatures:
                msg = (
                    f"YAML at {path} has a 'temperatures' section but no "
                    f"entry for {temperature} °C."
                )
                raise ValueError(msg)
            temp_data = temperatures[temperature]
        elif temperature != 25:
            msg = (
                f"YAML at {path} has no 'temperatures' section; cannot "
                f"honor request for {temperature} °C. Only the default "
                f"25 °C can be loaded."
            )
            raise ValueError(msg)
        else:
            temp_data = {}
        merged = {**d, **temp_data}
        available = tuple(sorted(int(k) for k in temperatures)) if temperatures else ()
        return cls._from_dict(merged, available_temperatures=available)

    @classmethod
    def default(cls) -> te.Self:
        """Load the bundled default sensor data at 25 °C."""
        return cls.at_temperature(25)

    @classmethod
    def _from_dict(
        cls,
        d: dict[str, t.Any],
        available_temperatures: tuple[int, ...] = (),
    ) -> te.Self:
        has_current_breakdown = _detect_current_breakdown(d)

        sleep_currents = {
            cls.ApsSleepState[k]: _scb_from_value(v) for k, v in d["sleep_currents"].items()
        }
        aps_idle_currents = {
            cls.ApsIdleState[k]: _scb_from_value(v) for k, v in d["aps_idle_currents"].items()
        }
        idle_currents_hf_wfi = {
            a2.IdleState[k]: _scb_from_value(v) for k, v in d["idle_currents"].items()
        }
        aps_active_currents = {
            cls.ApsActiveState[k]: _scb_from_value(v) for k, v in d["aps_active_currents"].items()
        }
        measure_model = _load_measure_model(d["aps_hf_wfi_rs_measure_model"])
        model_is_split = any(set(coeffs) != {_TOTAL_KEY} for coeffs in measure_model.values())
        if model_is_split != has_current_breakdown:
            msg = (
                "The measure model is split per component but the currents are totals."
                if model_is_split
                else "The currents are split per component but the measure model is a total."
            )
            raise ValueError(msg)

        # Derived: RS-only idle currents
        rs_idle_currents = {
            a2.IdleState.ARMED: (
                idle_currents_hf_wfi[a2.IdleState.ARMED]
                - aps_idle_currents[cls.ApsIdleState.APS_HF_WFI]
            ),
            a2.IdleState.READY: (
                idle_currents_hf_wfi[a2.IdleState.READY]
                - aps_idle_currents[cls.ApsIdleState.APS_HF_WFI]
            ),
        }
        hsm_offset_total = d.get("hsm_armed_offset_total", d.get("hsm_armed_offset", 0.0))
        rs_idle_currents_hsm = {
            a2.IdleState.ARMED: (rs_idle_currents[a2.IdleState.ARMED] + _bd(hsm_offset_total)),
            a2.IdleState.READY: rs_idle_currents[a2.IdleState.READY],
        }

        # Derived: measure(profile, prf) = intercept + slope * prf_mhz - aps_idle[HF_WFI]
        # Combinations rejected by config validation get extrapolated values
        aps_hf_wfi = aps_idle_currents[cls.ApsIdleState.APS_HF_WFI]
        measure_currents = {
            profile: {
                prf: (
                    CurrentBreakdown(
                        {
                            component: intercept + slope_per_mhz * prf.frequency / 1e6
                            for component, (intercept, slope_per_mhz) in coeffs.items()
                        }
                    )
                    - aps_hf_wfi
                )
                for prf in a2.PRF
            }
            for profile, coeffs in measure_model.items()
        }

        # RX antenna current
        rx_antenna = {
            a2.Profile(pk): {ck: _scb_from_value(cv) for ck, cv in channels.items()}
            for pk, channels in d["rx_antenna_current"].items()
        }

        # APS active as string-keyed for transition references
        aps_active_by_name = {k: _scb_from_value(v) for k, v in d["aps_active_currents"].items()}

        # Sleep/wakeup state transitions
        aps_sleep_wakeup = {
            cls.ApsSleepState[k]: _load_transition(v)
            for k, v in d["aps_sleep_wakeup_state"].items()
        }
        aps_go_to_sleep = {
            cls.ApsSleepState[k]: _load_transition(v)
            for k, v in d["aps_go_to_sleep_state"].items()
        }

        # Named state transitions
        transition_names = [
            "calibration_state",
            "radar_prepare_state",
            "radar_prepare_rs_init_state",
            "radar_power_on_state",
            "radar_power_off_state",
            "aps_lf_to_hf_state",
            "aps_mf_to_hf_state",
            "aps_hf_to_lf_state",
            "aps_hf_to_mf_state",
        ]
        transitions = {
            name: _load_transition(d[name], aps_active_by_name) for name in transition_names
        }

        # Sample durations
        sample_durations = {
            a2.Profile(pk): {a2.PRF[prf_name]: float(dur) for prf_name, dur in prfs.items()}
            for pk, prfs in d["sample_durations"].items()
        }

        return cls(
            aps_active_currents=aps_active_currents,
            aps_sleep_wakeup_state=aps_sleep_wakeup,
            aps_go_to_sleep_state=aps_go_to_sleep,
            idle_currents=idle_currents_hf_wfi,
            inter_sweep_currents=rs_idle_currents,
            inter_sweep_currents_hsm=rs_idle_currents_hsm,
            inter_frame_rs_currents=rs_idle_currents,
            inter_frame_aps_currents={
                **sleep_currents,  # type: ignore[dict-item]
                **aps_idle_currents,  # type: ignore[dict-item]
            },
            measure_currents=measure_currents,
            rx_antenna_current=rx_antenna,
            **transitions,
            frame_overhead=d["frame_overhead"],
            frame_overhead_hsm=d["frame_overhead_hsm"],
            sweep_setup_times={a2.IdleState[k]: v for k, v in d["sweep_setup_times"].items()},
            subsweep_setup_times_hsm={
                a2.IdleState[k]: v for k, v in d["subsweep_setup_times_hsm"].items()
            },
            subsweep_setup_time=d["subsweep_setup_time"],
            subsweep_setup_time_loopback=d["subsweep_setup_time_loopback"],
            sample_durations=sample_durations,
            jitter_compensation_duration=d["jitter_compensation_duration"],
            iq_processing_fixed=d["iq_processing_fixed"],
            iq_processing_per_point=d["iq_processing_per_point"],
            capon_processing_per_param=d["capon_processing_per_param"],
            capon_update_per_point=d["capon_update_per_point"],
            coherent_processing_per_param=d["coherent_processing_per_param"],
            coherent_update_per_point=d["coherent_update_per_point"],
            conventional_processing_per_param=d["conventional_processing_per_param"],
            conventional_update_per_point=d["conventional_update_per_point"],
            robust_capon_processing_per_param=d["robust_capon_processing_per_param"],
            robust_capon_update_per_point=d["robust_capon_update_per_point"],
            has_current_breakdown=has_current_breakdown,
            available_temperatures=available_temperatures,
        )
