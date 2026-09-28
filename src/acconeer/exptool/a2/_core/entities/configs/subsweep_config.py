# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved
from __future__ import annotations

import warnings

import attrs
import attrs.validators as av
import numpy as np
import numpy.typing as npt
from attributes_doc import attributes_doc

import acconeer.exptool.type_migration as tm
from acconeer.exptool._core.class_creation.mixins import AttrsMappingTransformsMixin
from acconeer.exptool._core.entities.validation_result import (
    ValidationError,
    ValidationResult,
    ValidationWarning,
)

from .config_enums import PRF, Profile


MAX_N_TABLE_ENTRIES = 22  # Memory constraint from c world.

_PRF_27_7_MHZ_MAX_ENDPOINT = 960
_PRF_20_8_MHZ_MAX_ENDPOINT = 1680
_PRF_15_8_MHZ_MAX_ENDPOINT = 2640
_PRF_12_5_MHZ_MAX_ENDPOINT = 3600
_PRF_8_3_MHZ_MAX_ENDPOINT = 6000
_PRF_5_3_MHZ_MAX_ENDPOINT = 10008

# PRFs a profile cannot use with TX enabled (exceeds 10% duty cycle).
UNSUPPORTED_TX_PRFS: dict[Profile, frozenset[PRF]] = {
    Profile.PROFILE_7: frozenset({PRF.PRF_27_7_MHZ}),
}

MIN_START_POINT = -200
MAX_START_POINT = 12000

MIN_NUM_POINTS = 1
MAX_NUM_POINTS = 2**16 - 1

MIN_STEP_LENGTH = 1
MAX_STEP_LENGTH = 3072

MIN_ANTENNA_MASK = 0b0001
MAX_TX_ANTENNA_MASK = 0b0111
MAX_RX_ANTENNA_MASK = 0b1111
MAX_NUM_CHANNELS = MAX_TX_ANTENNA_MASK.bit_count() * MAX_RX_ANTENNA_MASK.bit_count()

MIN_HWAAS = 1
MAX_HWAAS = 2047
MIN_HWAAS_EXPONENT = 0
MAX_HWAAS_EXPONENT = 4

MIN_RECEIVER_GAIN = 0
MAX_RECEIVER_GAIN = 14


@attributes_doc
@attrs.mutable(kw_only=True)
class SubsweepConfig(AttrsMappingTransformsMixin):
    start_point: int = attrs.field(
        default=100, converter=int, validator=[av.ge(MIN_START_POINT), av.le(MAX_START_POINT)]
    )
    """
    The starting point of the sweep.
    The corresponding start in millimeter is approximately start_point * 2.5 mm.
    """

    num_points: int = attrs.field(
        default=40, converter=int, validator=[av.ge(MIN_NUM_POINTS), av.le(MAX_NUM_POINTS)]
    )
    """The number of data points to measure in a sweep. """

    step_length: int = attrs.field(
        default=16, converter=int, validator=[av.ge(MIN_STEP_LENGTH), av.le(MAX_STEP_LENGTH)]
    )
    """The number of steps to have between each data point."""

    profile: Profile = attrs.field(default=Profile.PROFILE_3, converter=Profile)
    """
    Profile to use

    Each profile consists of a number of settings for the sensor that configures
    the TX and RX paths. Lower profiles have higher depth resolution while
    higher profiles have higher SNR.
    """

    prf: PRF = attrs.field(default=PRF.PRF_20_8_MHZ, converter=PRF)
    """Pulse Repetition Frequency"""

    tx_antenna_mask: int = attrs.field(
        default=0b111,
        converter=int,
        validator=[av.ge(MIN_ANTENNA_MASK), av.le(MAX_TX_ANTENNA_MASK)],
    )
    """The active TX antenna mask"""

    rx_antenna_mask: int = attrs.field(
        default=0b1111,
        converter=int,
        validator=[av.ge(MIN_ANTENNA_MASK), av.le(MAX_RX_ANTENNA_MASK)],
    )
    """The active RX antenna mask"""

    hwaas_max: int = attrs.field(
        default=50, converter=int, validator=[av.ge(MIN_HWAAS), av.le(MAX_HWAAS)]
    )
    """
    Maximum Hardware accelerated average samples

    If hwaas_exponent is set to 0, this value will be used for all points in the sweep.
    """

    hwaas_min: int = attrs.field(
        default=1, converter=int, validator=[av.ge(MIN_HWAAS), av.le(MAX_HWAAS)]
    )
    """Minimum Hardware accelerated average samples

    Limits the minimum number of HWAAS used for one point.
    When the number of HWAAS is scaled with the distance,
    this value limits the minimum number of HWAAS used for one point
    """

    hwaas_exponent: int = attrs.field(
        default=0, converter=int, validator=[av.ge(MIN_HWAAS_EXPONENT), av.le(MAX_HWAAS_EXPONENT)]
    )
    """
    Hardware accelerated average samples exponent

    The hwaas_exponent parameter controls how HWAAS is scaled with respect to distance during a sweep.
    The scaling is determined by the formula:

      max(hwaas_min, hwaas_max * (d_n / d_end) ^ hwaas_exponent)

    where d_n is the distance at point n and d_end is the distance at the last point in the sweep.
    HWAAS-scaling compensates for the energy loss of the propagating signal as it travels to and from the target.

    Commonly used values:
      4: Use this for targets with a general shape. This accounts for the highest degree of energy dilution.
      2: Use this for large planar targets, such as flat surfaces, where energy spreads less.
      0: Use this to maintain constant HWAAS throughout the sweep. No scaling is applied, and HWAAS remains unchanged.
    """

    receiver_gain: int = attrs.field(
        default=10, converter=int, validator=[av.ge(MIN_RECEIVER_GAIN), av.le(MAX_RECEIVER_GAIN)]
    )
    """Receiver gain"""

    enable_tx: bool = attrs.field(default=True, converter=bool)
    """Enable tx"""

    @property
    def _rel_distances(self) -> npt.NDArray[np.float64]:
        """The relative distances. Last point is always 1.0."""
        return np.array(
            [
                (self.start_point + self.step_length * i) / self.end_point
                for i in range(self.num_points)
            ]
        )

    def _calc_scaled_hwaas(self) -> npt.NDArray[np.float64]:
        """Calculates the ideal hwaas values for the configuration."""
        if self.end_point <= 0:
            scaled_hwaas = self.hwaas_max * np.ones(self.num_points)
        else:
            scaled_hwaas = self.hwaas_max * (self._rel_distances**self.hwaas_exponent)
            scaled_hwaas = np.where(
                ((scaled_hwaas < self.hwaas_min) | (self._rel_distances <= 0)),
                self.hwaas_min,
                scaled_hwaas,
            )

        return scaled_hwaas

    @staticmethod
    def _get_dyn_hwaas_table(
        scaled_hwaas: npt.NDArray[np.float64], stepped_hwaas: npt.NDArray[np.int_]
    ) -> tuple[list[int], list[int]]:
        """Calculate the switch indexes and hwaas values at those indexes. Same as in C."""
        switch_point: list[int] = []
        hwaas: list[int] = []

        for point_idx, point_hwaas in enumerate(scaled_hwaas):
            idx = (
                np.abs(stepped_hwaas - point_hwaas)
            ).argmin()  # Get index of HWAAS level closest to ideal HWAAS
            if not hwaas:  # If array is empty
                hwaas.append(stepped_hwaas[idx])
            else:
                if hwaas[-1] != stepped_hwaas[idx]:
                    hwaas.append(stepped_hwaas[idx])
                    switch_point.append(point_idx)
        return switch_point, hwaas

    def _calc_stepped_hwaas(self, scaled_hwaas: npt.NDArray[np.float64]) -> npt.NDArray[np.int_]:
        """
        Calculate a log interpolation for the stepped hwaas values.
        The number of possible hwaas values is limited by MAX_N_TABLE_ENTRIES.
        This function tries to divide the interval into equal parts with equivalent snr increase in db.
        """

        first_hwaas_ln = float(np.log10(scaled_hwaas[0]))
        last_hwaas_ln = float(np.log10(scaled_hwaas[-1]))

        hwaas_step_ln = (last_hwaas_ln - first_hwaas_ln) / (MAX_N_TABLE_ENTRIES - 1)
        stepped_hwaas_ln = (
            np.arange(MAX_N_TABLE_ENTRIES).astype(np.float64) * hwaas_step_ln + first_hwaas_ln
        )

        stepped_hwaas: npt.NDArray[np.int_] = np.round(10**stepped_hwaas_ln).astype(np.int_)

        return stepped_hwaas

    @property
    def num_channels(self) -> int:
        """The number of channels based tx_antenna_mask and rx_antenna_mask"""
        return bin(self.tx_antenna_mask).count("1") * bin(self.rx_antenna_mask).count("1")

    @property
    def end_point(self) -> int:
        """The end point measured by this subsweep config"""
        return self.start_point + self.step_length * (self.num_points - 1)

    @property
    def hwaas_points(self) -> npt.NDArray[np.int_]:
        """The hwaas values used for each point."""
        if self.hwaas_exponent == 0:
            return np.full(self.num_points, self.hwaas_max)

        scaled_hwaas = self._calc_scaled_hwaas()
        stepped_hwaas = self._calc_stepped_hwaas(scaled_hwaas)

        # Same structure returned as in C code.
        switch_point, hwaas = self._get_dyn_hwaas_table(scaled_hwaas, stepped_hwaas)

        curr_start = 0
        ret_hwaas = np.zeros(self.num_points, dtype=int)
        # Construct the array from the C structures.
        for ind, switch in enumerate(switch_point):
            ret_hwaas[curr_start:switch] = hwaas[ind]
            curr_start = switch
        ret_hwaas[curr_start:] = hwaas[-1]
        return ret_hwaas

    def _collect_validation_results(self) -> list[ValidationResult]:
        validation_results: list[ValidationResult] = []

        if self.hwaas_exponent > 0 and self.hwaas_min > self.hwaas_max:
            validation_results.extend(
                [
                    ValidationError(
                        self, "hwaas_min", "hwaas_min must not be greater than hwaas_max"
                    ),
                ]
            )

        prf_err_msg = "PRF is too high for the end of the measured range. Try decreasing the PRF."
        measured_range_err_msg = (
            "The measured range stretches longer than the current PRF can measure."
        )
        num_points_err_msg = f"{measured_range_err_msg} Try decreasing num_points."
        step_length_err_msg = f"{measured_range_err_msg} Try decreasing step_length."
        start_point_err_msg = f"{measured_range_err_msg} Try decreasing start_point"

        if self.enable_tx and (
            (self.prf == PRF.PRF_27_7_MHZ and self.end_point > _PRF_27_7_MHZ_MAX_ENDPOINT)
            or (self.prf == PRF.PRF_20_8_MHZ and self.end_point > _PRF_20_8_MHZ_MAX_ENDPOINT)
            or (self.prf == PRF.PRF_15_8_MHZ and self.end_point > _PRF_15_8_MHZ_MAX_ENDPOINT)
            or (self.prf == PRF.PRF_12_5_MHZ and self.end_point > _PRF_12_5_MHZ_MAX_ENDPOINT)
            or (self.prf == PRF.PRF_8_3_MHZ and self.end_point > _PRF_8_3_MHZ_MAX_ENDPOINT)
            or (self.prf == PRF.PRF_5_3_MHZ and self.end_point > _PRF_5_3_MHZ_MAX_ENDPOINT)
        ):
            validation_results.extend(
                [
                    ValidationError(
                        source=self,
                        aspect="prf",
                        message=prf_err_msg,
                    ),
                    ValidationError(source=self, aspect="num_points", message=num_points_err_msg),
                    ValidationError(
                        source=self, aspect="step_length", message=step_length_err_msg
                    ),
                    ValidationError(
                        source=self, aspect="start_point", message=start_point_err_msg
                    ),
                ]
            )

        if self.enable_tx and self.prf in UNSUPPORTED_TX_PRFS.get(self.profile, frozenset()):
            validation_results.append(
                ValidationError(
                    source=self,
                    aspect="prf",
                    message=(
                        f"Profile {self.profile.value} with PRF {self.prf.frequency / 1e6:.1f} "
                        "MHz exceeds 10% duty cycle. Try decreasing the PRF."
                    ),
                )
            )

        return validation_results

    def validate(self) -> None:
        """Performs self-validation

        :raises ValidationError: If anything is invalid.
        """
        for validation_result in self._collect_validation_results():
            try:
                raise validation_result
            except ValidationWarning as vw:
                warnings.warn(vw.message)


@attrs.mutable(kw_only=True)
class _SubsweepConfig_w_enable_loopback(AttrsMappingTransformsMixin):
    start_point: int = attrs.field(default=100, converter=int)
    num_points: int = attrs.field(default=40, converter=int, validator=av.ge(0))
    step_length: int = attrs.field(default=16, converter=int, validator=av.gt(0))
    profile: Profile = attrs.field(default=Profile.PROFILE_3, converter=Profile)
    prf: PRF = attrs.field(default=PRF.PRF_20_8_MHZ, converter=PRF)
    tx_antenna_mask: int = attrs.field(
        default=0b111, converter=int, validator=av.in_(range(0b111 + 1))
    )
    rx_antenna_mask: int = attrs.field(
        default=0b1111, converter=int, validator=av.in_(range(0b1111 + 1))
    )
    hwaas_max: int = attrs.field(default=50, converter=int, validator=av.in_(range(1, 2047 + 1)))
    hwaas_min: int = attrs.field(default=1, converter=int, validator=av.in_(range(1, 2047 + 1)))
    hwaas_exponent: int = attrs.field(default=0, converter=int, validator=av.in_(range(4 + 1)))
    receiver_gain: int = attrs.field(default=10, converter=int, validator=av.in_(range(14 + 1)))
    enable_tx: bool = attrs.field(default=True, converter=bool)
    enable_loopback: bool = attrs.field(default=False, converter=bool)


@attrs.mutable(kw_only=True)
class _SubsweepConfig_pre_dynamic_hwaas(AttrsMappingTransformsMixin):
    start_point: int = attrs.field(default=100, converter=int)
    num_points: int = attrs.field(default=40, converter=int, validator=av.ge(0))
    step_length: int = attrs.field(default=16, converter=int, validator=av.gt(0))
    profile: Profile = attrs.field(default=Profile.PROFILE_3, converter=Profile)
    prf: PRF = attrs.field(default=PRF.PRF_20_8_MHZ, converter=PRF)
    tx_antenna_mask: int = attrs.field(
        default=0b111, converter=int, validator=av.in_(range(0b111 + 1))
    )
    rx_antenna_mask: int = attrs.field(
        default=0b1111, converter=int, validator=av.in_(range(0b1111 + 1))
    )
    hwaas: int = attrs.field(default=50, converter=int, validator=av.in_(range(1, 2047 + 1)))
    receiver_gain: int = attrs.field(default=10, converter=int, validator=av.in_(range(14 + 1)))
    enable_tx: bool = attrs.field(default=True, converter=bool)


_loopback_subtree = (
    tm.start(_SubsweepConfig_w_enable_loopback)
    .load(dict, _SubsweepConfig_w_enable_loopback.from_dict, fail=[TypeError])
    .load(str, _SubsweepConfig_w_enable_loopback.from_json, fail=tm.common_exceptions.FROM_JSON)
    .epoch(
        SubsweepConfig,
        lambda old: SubsweepConfig(
            hwaas_max=old.hwaas_max,
            hwaas_min=old.hwaas_min,
            hwaas_exponent=old.hwaas_exponent,
            start_point=old.start_point,
            num_points=old.num_points,
            step_length=old.step_length,
            profile=old.profile,
            prf=old.prf,
            tx_antenna_mask=old.tx_antenna_mask,
            rx_antenna_mask=old.rx_antenna_mask,
            receiver_gain=old.receiver_gain,
            enable_tx=old.enable_tx,
        ),
        fail=[TypeError, ValueError],
    )
)

subsweep_config_timeline = (
    tm.start(_SubsweepConfig_pre_dynamic_hwaas)
    .load(dict, _SubsweepConfig_pre_dynamic_hwaas.from_dict, fail=[TypeError])
    .load(str, _SubsweepConfig_pre_dynamic_hwaas.from_json, fail=tm.common_exceptions.FROM_JSON)
    .epoch(
        SubsweepConfig,
        lambda old: SubsweepConfig(
            hwaas_max=old.hwaas,
            hwaas_min=1,
            hwaas_exponent=0,
            start_point=old.start_point,
            num_points=old.num_points,
            step_length=old.step_length,
            profile=old.profile,
            prf=old.prf,
            tx_antenna_mask=old.tx_antenna_mask,
            rx_antenna_mask=old.rx_antenna_mask,
            receiver_gain=old.receiver_gain,
            enable_tx=old.enable_tx,
        ),
        fail=[TypeError, ValueError],
    )
    .load(dict, SubsweepConfig.from_dict, fail=[TypeError])
    .load(str, SubsweepConfig.from_json, fail=tm.common_exceptions.FROM_JSON)
    .load(
        _SubsweepConfig_w_enable_loopback,
        _loopback_subtree.migrate,
        fail=[tm.MigrationError],
    )
    .load(dict, _loopback_subtree.migrate, fail=[tm.MigrationError])
    .load(str, _loopback_subtree.migrate, fail=[tm.MigrationError])
)
