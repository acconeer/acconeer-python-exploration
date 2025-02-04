# Copyright (c) Acconeer AB, 2023-2025
# All rights reserved

from __future__ import annotations

import typing as t

from acconeer.exptool import a121

from .preview import PresentationType


_DISCLAIMER = """
This snippet is generated to be compatible with RSS A121 v1.0.0
If there is a version missmatch the snippet might need some modification
"""


def _sensor_config_parameters(config: a121.SensorConfig) -> str:
    return "\n".join(
        f"acc_config_{attr}_set(config, {value});"
        for attr, value in {
            "sweeps_per_frame": _uint(config.sweeps_per_frame),
            "sweep_rate": _rate(config.sweep_rate),
            "frame_rate": _rate(config.frame_rate),
            "inter_sweep_idle_state": _idle_state(config.inter_sweep_idle_state),
            "inter_frame_idle_state": _idle_state(config.inter_frame_idle_state),
            "continuous_sweep_mode": _bool(config.continuous_sweep_mode),
            "double_buffering": _bool(config.double_buffering),
        }.items()
    )


def _subsweep_parameters(config: a121.SubsweepConfig, *, index: t.Optional[int]) -> str:
    return "\n".join(
        [
            (
                f"acc_config_{attr}_set(config, {value});"
                if index is None
                else f"acc_config_subsweep_{attr}_set(config, {value}, {_uint(index)});"
            )
            for attr, value in {
                "start_point": config.start_point,
                "num_points": _uint(config.num_points),
                "step_length": _uint(config.step_length),
                "profile": _profile(config.profile),
                "hwaas": _uint(config.hwaas),
                "receiver_gain": _uint(config.receiver_gain),
                "enable_tx": _bool(config.enable_tx),
                "enable_loopback": _bool(config.enable_loopback),
                "phase_enhancement": _bool(config.phase_enhancement),
                "iq_imbalance_compensation": _bool(config.iq_imbalance_compensation),
                "prf": _prf(config.prf),
            }.items()
        ]
    )


def _idle_state(idle_state: a121.IdleState) -> str:
    return f"ACC_CONFIG_IDLE_STATE_{idle_state.name}".upper()


def _prf(prf: a121.PRF) -> str:
    return f"ACC_CONFIG_{prf.name}".upper()


def _profile(profile: a121.Profile) -> str:
    return f"ACC_CONFIG_{profile.name}"


def _uint(number: int) -> str:
    return f"{number}U"


def _rate(number: t.Optional[float]) -> str:
    return "0.0f" if number is None else f"{number:.3f}f"


def _bool(flag: bool) -> str:
    return str(flag).lower()


def _indent(body: str, indent: str = "\t") -> str:
    return indent + body.strip().replace("\n", "\n" + indent)


def _frame_it(function_body: str) -> str:
    return (
        "static void set_config(acc_config_t *config)\n"
        + "{\n"
        + _indent(_DISCLAIMER, indent="\t// ")
        + "\n"
        + "\n"
        + _indent(function_body)
        + "\n"
        + "}\n"
    )


def set_config_presenter(instance: t.Any, t: PresentationType) -> t.Optional[str]:
    if t is not PresentationType.C_SET_CONFIG:
        return None

    if isinstance(instance, a121.SessionConfig):
        try:
            instance = instance.sensor_config
        except RuntimeError:
            return None

    if isinstance(instance, a121.SensorConfig):
        if instance.num_subsweeps == 1:
            return _frame_it(
                _subsweep_parameters(instance.subsweep, index=None)
                + "\n"
                + "\n"
                + _sensor_config_parameters(instance)
            )
        else:
            return _frame_it(
                "\n\n".join(
                    [
                        _sensor_config_parameters(instance),
                        f"acc_config_num_subsweeps_set(config, {_uint(instance.num_subsweeps)});",
                    ]
                    + [
                        (f"// Subsweep {i}\n" + _subsweep_parameters(ssc, index=i))
                        for i, ssc in enumerate(instance.subsweeps)
                    ]
                )
            )

    return None
