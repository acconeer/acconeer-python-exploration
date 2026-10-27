# Copyright (c) Acconeer AB, 2026
# All rights reserved

"""Where the sensor is mounted and what to detect, as two persisted configs.

* :class:`SensorInstallation`: how the sensor is mounted.
* :class:`DetectionVolume`: the region to detect within.

World frame
    Right-handed, in meters, with **z up** and the origin at the sensor.

Sensor frame
    The sensor's own frame, with the origin at the sensor: boresight along
    +y, +x toward positive azimuth, +z toward positive elevation.

Map points between the two with :meth:`SensorInstallation.sensor_to_world`
and :meth:`SensorInstallation.world_to_sensor`.
"""

from __future__ import annotations

import json
import typing as t
import warnings

import attrs
import attrs.validators as av
import h5py
import numpy as np
import numpy.typing as npt
from attributes_doc import attributes_doc

from acconeer.exptool._core.class_creation.mixins import AttrsMappingTransformsMixin
from acconeer.exptool._core.entities.validation_result import (
    ValidationError,
    ValidationResult,
    ValidationWarning,
)
from acconeer.exptool.a2.algo.nodes._heatmap_peak_nodes import ExclusionZone
from acconeer.exptool.a2.algo.nodes._spherical_to_cartesian_nodes import (
    RotationMatrix,
    build_mount_rotation_matrix,
)


# Physical upper bound on configured ranges for the motion-detection/presence-tracking
# processors. Also used as the absolute cap on x/y/z bounds: the processors do no
# translation (only optional rotation), so any detected point sits within this radial
# range and therefore each axis is bounded by ±MAX_RANGE_M.
MAX_RANGE_M = 10.0

DEFAULT_AZ_ANGLE_RANGE = (-60.0, 60.0)
DEFAULT_EL_ANGLE_RANGE = (-30.0, 30.0)
# Floor-to-ceiling height of the room the sensor is mounted in. The detection
# volume's box bounds only x and y; it is taken as high as the room when
# sizing the range to measure (see _shared_config.room_z_bounds_m).
DEFAULT_ROOM_HEIGHT_M = 2.5
# About the chest height of a person, above the floor.
CHEST_HEIGHT_M = 1.2

SENSOR_INSTALLATION_DATASET_NAME = "sensor_installation"
DETECTION_VOLUME_DATASET_NAME = "detection_volume"
# Recordings made before the split hold one ``DetectionVolumeConfig`` dataset;
# see split_legacy_detection_volume_config.
LEGACY_DETECTION_VOLUME_CONFIG_DATASET_NAME = "detection_volume_config"

# How a legacy DetectionVolumeConfig splits up. It held no mount height, so
# the installation takes the floor to be its box's bottom. Its z bounds are
# otherwise dropped, as the box bounds only x and y.
_LEGACY_ROTATION_KEYS = ("x_rotation", "y_rotation", "z_rotation")
_LEGACY_VOLUME_KEYS = (
    "x_bounds_m",
    "y_bounds_m",
    "az_angle_range",
    "el_angle_range",
)
# DetectionVolume fields that recordings may still hold but that are gone:
# the box had a height until it bounded only x and y.
_REMOVED_VOLUME_KEYS = ("z_bounds_m",)

_NDf64 = npt.NDArray[np.float64]


def _to_float_pair(v: t.Iterable[float]) -> tuple[float, float]:
    a, b = v
    return float(a), float(b)


def _to_optional_float_pair(v: t.Iterable[float] | None) -> tuple[float, float] | None:
    return None if v is None else _to_float_pair(v)


def _to_exclusion_zones(
    v: t.Iterable[ExclusionZone | t.Mapping[str, t.Any]],
) -> tuple[ExclusionZone, ...]:
    # Also accepts the dict form produced by to_dict/to_json, so a recorded
    # config loads back with its zones.
    zones = []
    for zone in v:
        if isinstance(zone, ExclusionZone):
            center, radius_m = zone.center, zone.radius_m
        else:
            center, radius_m = zone["center"], zone["radius_m"]
        zones.append(ExclusionZone(center=_to_float_pair(center), radius_m=float(radius_m)))
    return tuple(zones)


def _ordered_pair(instance: t.Any, attribute: t.Any, value: tuple[float, float]) -> None:
    lo, hi = value
    if lo >= hi:
        msg = f"{attribute.name}: lower bound {lo} must be smaller than upper bound {hi}."
        raise ValueError(msg)


def _is_legacy_detection_volume_config(dict_repr: dict[str, t.Any]) -> bool:
    """Whether ``dict_repr`` holds both box bounds and rotations, as only a
    legacy ``DetectionVolumeConfig`` does."""
    return "x_bounds_m" in dict_repr and any(key in dict_repr for key in _LEGACY_ROTATION_KEYS)


def _legacy_installation_kwargs(legacy: dict[str, t.Any]) -> dict[str, t.Any]:
    return {
        **{key: legacy[key] for key in _LEGACY_ROTATION_KEYS if key in legacy},
        "mount_height_m": -float(legacy["z_bounds_m"][0]),
    }


def _legacy_volume_kwargs(legacy: dict[str, t.Any]) -> dict[str, t.Any]:
    return {key: legacy[key] for key in _LEGACY_VOLUME_KEYS if key in legacy}


def _optional_in_max_range(
    instance: t.Any, attribute: t.Any, value: tuple[float, float] | None
) -> None:
    if value is None:
        return
    _ordered_pair(instance, attribute, value)
    lo, hi = value
    if lo < -MAX_RANGE_M or hi > MAX_RANGE_M:
        msg = (
            f"{attribute.name}: bounds ({lo}, {hi}) must lie within "
            f"[-{MAX_RANGE_M}, {MAX_RANGE_M}]."
        )
        raise ValueError(msg)


@attributes_doc
@attrs.mutable
class SensorInstallation(AttrsMappingTransformsMixin):
    """How the sensor is mounted, in the world frame.

    The mount rotation starts with the sensor aligned with the world (``+x``
    right, ``+y`` boresight, ``+z`` up), so its original axes are the world's
    axes, and rotates it about those fixed axes by ``y_rotation`` (roll), then
    ``x_rotation`` (tilt), then ``z_rotation`` (pan), each right-handed:
    ``p_world = Rz(z_rotation) @ Rx(x_rotation) @ Ry(y_rotation) @ p_sensor``.
    """

    y_rotation: float = attrs.field(default=180.0)
    """Roll, i.e. rotation about the sensor's original y-axis (boresight
    direction) in degrees, applied first. Roll does not move the boresight,
    but it flips how ``x_rotation``/``z_rotation`` relate to the sensor's own
    azimuth and elevation.

    Only 0 and 180 are supported."""

    x_rotation: float = attrs.field(default=0.0)
    """Tilt, i.e. rotation about the sensor's original x-axis in degrees,
    applied after ``y_rotation``. Positive tilt turns the boresight up in the
    world.

    With ``y_rotation=0`` this is toward positive elevation; with
    ``y_rotation=180`` the sensor is upside down, so it is toward negative
    elevation."""

    z_rotation: float = attrs.field(default=0.0)
    """Pan, i.e. rotation about the sensor's original z-axis (the world's
    vertical) in degrees, applied last. Positive pan turns the boresight
    toward ``-x``.

    With no tilt, a pan of ``+θ`` moves the boresight to sensor azimuth ``-θ``
    with ``y_rotation=0``, or ``+θ`` with ``y_rotation=180``."""

    mount_height_m: float = attrs.field(kw_only=True, validator=av.ge(0.0))
    """Height of the sensor above the floor, in meters."""

    @classmethod
    def from_dict(cls, dict_repr: dict[str, t.Any]) -> t.Self:
        """Also accepts a legacy ``DetectionVolumeConfig``, as the old Detection
        Volume editor saved it, and takes its rotations; see
        :func:`split_legacy_detection_volume_config`."""
        if _is_legacy_detection_volume_config(dict_repr):
            return cls(**_legacy_installation_kwargs(dict_repr))
        return super().from_dict(dict_repr)

    @property
    def mount_rotation(self) -> RotationMatrix:
        """Rotation from sensor-frame to world-frame axes, built from the three rotations."""
        return build_mount_rotation_matrix(
            x_rotation=self.x_rotation, y_rotation=self.y_rotation, z_rotation=self.z_rotation
        )

    def sensor_to_world(self, points_m: npt.ArrayLike) -> _NDf64:
        """World positions of sensor-frame points, along the last axis."""
        return self.mount_rotation.apply(points_m)

    def world_to_sensor(self, points_m: npt.ArrayLike) -> _NDf64:
        """Sensor-frame positions of world points, along the last axis;
        inverse of :meth:`sensor_to_world`."""
        return self.mount_rotation.apply_inverse(points_m)

    def _collect_validation_results(self) -> list[ValidationResult]:
        if self.y_rotation not in (0.0, 180.0):
            return [
                ValidationWarning(
                    self,
                    "y_rotation",
                    f"y_rotation is {self.y_rotation:.1f}°; only 0° and 180° are supported.",
                )
            ]
        return []

    def validate(self) -> None:
        """Raise the first ``ValidationError``, emit ``ValidationWarning``
        results via the ``warnings`` system."""
        for validation_result in self._collect_validation_results():
            try:
                raise validation_result
            except ValidationWarning as vw:
                warnings.warn(vw.message)


@attributes_doc
@attrs.mutable
class DetectionVolume(AttrsMappingTransformsMixin):
    """Region to detect within, the intersection of:

    * a box in the world frame, bounded in x and y only: ``x_bounds_m`` and
      ``y_bounds_m``;
    * a sector in the sensor frame's spherical coordinates (range, azimuth, elevation):
      ``start_m``, ``end_m``, ``az_angle_range``, and ``el_angle_range``.

    The box is bounded in x and y together or not at all.
    Either bound the box or set ``end_m``, so that the region has a farthest
    point. Where the box and ``start_m``/``end_m`` both limit the range from
    the sensor, the stricter one applies. Detections inside any of the
    ``exclusion_zones`` are dropped.
    """

    x_bounds_m: tuple[float, float] | None = attrs.field(
        default=None, converter=_to_optional_float_pair, validator=_optional_in_max_range
    )
    """``(lo, hi)`` world x extent of the box, in meters, or ``None`` for no
    box. Set together with ``y_bounds_m``."""

    y_bounds_m: tuple[float, float] | None = attrs.field(
        default=None, converter=_to_optional_float_pair, validator=_optional_in_max_range
    )
    """``(lo, hi)`` world y extent of the box, in meters, or ``None`` for no
    box. Set together with ``x_bounds_m``."""

    start_m: float | None = attrs.field(
        default=None,
        validator=av.optional([av.ge(0.0), av.lt(MAX_RANGE_M)]),
    )
    """Range (distance from the sensor) where detection starts, in meters, or ``None``."""

    end_m: float | None = attrs.field(
        default=None,
        validator=av.optional([av.gt(0.0), av.le(MAX_RANGE_M)]),
    )
    """Range (distance from the sensor) where detection ends, in meters, or ``None``."""

    az_angle_range: tuple[float, float] = attrs.field(
        default=DEFAULT_AZ_ANGLE_RANGE, converter=_to_float_pair, validator=_ordered_pair
    )
    """``(lo, hi)`` azimuth angle range in degrees, in the sensor frame."""

    el_angle_range: tuple[float, float] = attrs.field(
        default=DEFAULT_EL_ANGLE_RANGE, converter=_to_float_pair, validator=_ordered_pair
    )
    """``(lo, hi)`` elevation angle range in degrees, in the sensor frame."""

    exclusion_zones: tuple[ExclusionZone, ...] = attrs.field(
        factory=tuple, converter=_to_exclusion_zones
    )
    """Circular regions in the world xy plane whose detections are dropped.
    Empty (the default) disables exclusion."""

    @classmethod
    def from_dict(cls, dict_repr: dict[str, t.Any]) -> t.Self:
        """Also accepts a legacy ``DetectionVolumeConfig``, as the old Detection
        Volume editor saved it, and takes its box and angle ranges; see
        :func:`split_legacy_detection_volume_config`. Drops fields that are
        gone, such as ``z_bounds_m``, so older recordings still load."""
        if _is_legacy_detection_volume_config(dict_repr):
            return cls(**_legacy_volume_kwargs(dict_repr))
        return super().from_dict(
            {key: value for key, value in dict_repr.items() if key not in _REMOVED_VOLUME_KEYS}
        )

    def _collect_validation_results(self) -> list[ValidationResult]:
        results: list[ValidationResult] = []
        if self._has_box:
            for name, bounds in (("x_bounds_m", self.x_bounds_m), ("y_bounds_m", self.y_bounds_m)):
                if bounds is None:
                    results.append(
                        ValidationError(
                            self,
                            name,
                            f"Set {name} too: the box is bounded in x and y together "
                            "or not at all.",
                        )
                    )
        elif self.end_m is None:
            results.append(
                ValidationError(
                    self,
                    "end_m",
                    "The detection volume has no farthest point. Set end_m, or bound the box.",
                )
            )
        if self.start_m is not None and self.end_m is not None and self.start_m >= self.end_m:
            results.append(
                ValidationError(
                    self,
                    "start_m",
                    f"start_m ({self.start_m:.2f} m) must be smaller than end_m "
                    f"({self.end_m:.2f} m).",
                )
            )

        # Az/el limits must lie strictly inside (-90, 90) so the spherical
        # inverse used by the boundary check remains single-valued after
        # the state is rotated into the sensor frame.
        for name, (lo, hi) in (
            ("az_angle_range", self.az_angle_range),
            ("el_angle_range", self.el_angle_range),
        ):
            if lo <= -90.0 or hi >= 90.0:
                results.append(
                    ValidationError(
                        self,
                        name,
                        f"{name}: bounds ({lo}, {hi}) must lie strictly inside "
                        f"(-90, 90) degrees; the sensor's field of view is at "
                        f"most a 180-degree hemisphere.",
                    )
                )
        return results

    def validate(self) -> None:
        """Raise the first ``ValidationError``, if any."""
        for result in self._collect_validation_results():
            raise result

    @property
    def _has_box(self) -> bool:
        return self.x_bounds_m is not None or self.y_bounds_m is not None


def split_legacy_detection_volume_config(
    json_str: str,
) -> tuple[SensorInstallation, DetectionVolume]:
    """Split a recorded ``DetectionVolumeConfig`` into the two configs.

    The rotations go to the installation, with the box's bottom as the floor,
    as legacy recordings do not store ``mount_height_m``. The box's x and y
    bounds and the angle ranges go to the volume, without ``start_m``/``end_m``,
    and its z bounds are dropped. The legacy box was relative to the sensor, as the
    world frame is, so it carries over unchanged.
    """
    legacy = json.loads(json_str)
    return (
        SensorInstallation(**_legacy_installation_kwargs(legacy)),
        DetectionVolume(**_legacy_volume_kwargs(legacy)),
    )


def save_detection_geometry(
    group: h5py.Group, installation: SensorInstallation, volume: DetectionVolume
) -> None:
    """Write ``installation`` and ``volume`` as datasets in ``group``."""
    group.create_dataset(SENSOR_INSTALLATION_DATASET_NAME, data=installation.to_json())
    group.create_dataset(DETECTION_VOLUME_DATASET_NAME, data=volume.to_json())


def load_detection_geometry(
    group: h5py.Group,
) -> tuple[SensorInstallation, DetectionVolume] | None:
    """Read what :func:`save_detection_geometry` wrote to ``group``, or split
    a legacy ``detection_volume_config`` dataset (see
    :func:`split_legacy_detection_volume_config`). ``None`` if ``group``
    holds neither.
    """
    installation_dataset = group.get(SENSOR_INSTALLATION_DATASET_NAME)
    volume_dataset = group.get(DETECTION_VOLUME_DATASET_NAME)
    if installation_dataset is not None and volume_dataset is not None:
        return (
            SensorInstallation.from_json(installation_dataset[()].decode()),
            DetectionVolume.from_json(volume_dataset[()].decode()),
        )
    legacy_dataset = group.get(LEGACY_DETECTION_VOLUME_CONFIG_DATASET_NAME)
    if legacy_dataset is not None:
        return split_legacy_detection_volume_config(legacy_dataset[()].decode())
    return None
