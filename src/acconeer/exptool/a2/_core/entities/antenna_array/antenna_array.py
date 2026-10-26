# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved
from __future__ import annotations

import typing as t
from enum import Enum

import attrs
import attrs.validators as av
import numpy as np
import numpy.typing as npt
import typing_extensions as te

from acconeer.exptool._core.class_creation.attrs import attrs_dict_ndarray_isclose
from acconeer.exptool._core.class_creation.enum import find_by_name
from acconeer.exptool.a2._core import channel_convention as ch_conv
from acconeer.exptool.a2._core.entities.configs.config_enums import Profile

from .chebychev_compensations import (
    CHEB_CORR_AP212_R2_PROFILE_3,
    CHEB_CORR_AP212_R2_PROFILE_6,
)


WAVELENGTH_MM = 299792458.0 / 60.5e9 * 1000

# Profiles 1-5 use the table fitted to profile 3, profiles 6-7 the one fitted to profile 6
_AP212_R2_CHEB_CORR = {
    Profile.PROFILE_1: CHEB_CORR_AP212_R2_PROFILE_3,
    Profile.PROFILE_2: CHEB_CORR_AP212_R2_PROFILE_3,
    Profile.PROFILE_3: CHEB_CORR_AP212_R2_PROFILE_3,
    Profile.PROFILE_4: CHEB_CORR_AP212_R2_PROFILE_3,
    Profile.PROFILE_5: CHEB_CORR_AP212_R2_PROFILE_3,
    Profile.PROFILE_6: CHEB_CORR_AP212_R2_PROFILE_6,
    Profile.PROFILE_7: CHEB_CORR_AP212_R2_PROFILE_6,
}


def _tables_by_profile(
    tables: t.Mapping[t.Any, npt.ArrayLike],
) -> dict[Profile, npt.NDArray[np.complex128]]:
    # Profiles that share a table share one array
    arrays = {id(table): np.asarray(table) for table in tables.values()}
    return {Profile(profile): arrays[id(table)] for profile, table in tables.items()}


def _validate_has_all_profiles(
    _: t.Any, attr: attrs.Attribute[t.Any], value: t.Mapping[Profile, t.Any]
) -> None:
    missing = [profile.name for profile in Profile if profile not in value]
    if missing:
        msg = f"{attr.name} has no table for {', '.join(missing)}"
        raise ValueError(msg)


@attrs.frozen
class Pos:
    """Simple representation of a position in 3D-space.

    A ``Pos`` can be unpacked to its components:

    >>> x, y, z = Pos(1, 2, 3)
    >>> (x, y, z)
    (1.0, 2.0, 3.0)

    And added to another ``Pos``:

    >>> Pos(1, 2, 3) + Pos(-1, -2, -3)
    Pos(x=0.0, y=0.0, z=0.0)
    """

    x: float = attrs.field(converter=float)
    y: float = attrs.field(converter=float)
    z: float = attrs.field(converter=float)

    @classmethod
    def origin(cls) -> te.Self:
        return cls(0, 0, 0)

    def __iter__(self) -> t.Iterator[float]:
        yield from attrs.astuple(self)

    def __add__(self, other: t.Any) -> Pos:
        if not isinstance(other, Pos):
            return NotImplemented

        return Pos(self.x + other.x, self.y + other.y, self.z + other.z)


@attrs.frozen
class Channel:
    """A channel is a combination of a Tx antenna and an Rx antenna"""

    tx: Pos
    rx: Pos

    @property
    def position(self) -> Pos:
        """The channel position is the sum of the tx- & rx positions"""
        return self.tx + self.rx


def _raise_type_error(_: t.Any, attr: attrs.Attribute[t.Any], value: t.Any) -> None:
    msg = f"Cannot change field {attr.name!r}. Instance is frozen."
    raise TypeError(msg)


# This construct makes the class kind-of frozen.
# It's needed to play well with the AntennaArray enum below
@attrs.mutable(on_setattr=_raise_type_error)
class _AntennaArrayData:
    """Representation of an antenna array

    This class is used to calculate channel positions & steering vectors
    """

    txs: t.Mapping[int, Pos] = attrs.field(
        validator=av.deep_mapping(av.instance_of(int), av.instance_of(Pos))
    )
    rxs: t.Mapping[int, Pos] = attrs.field(
        validator=av.deep_mapping(av.instance_of(int), av.instance_of(Pos))
    )
    # One correction table per profile. The converter normalizes the tables to ndarrays once at
    # construction, instead of get_correction_scalar re-converting them on every call.
    antenna_cheb_corr: t.Mapping[Profile, npt.NDArray[np.complex128]] = attrs.field(
        converter=_tables_by_profile,
        validator=_validate_has_all_profiles,
        eq=attrs_dict_ndarray_isclose,
    )

    @property
    def physical_tx_mask(self) -> int:
        return self._antenna_indexes_to_mask(self.txs.keys())

    @property
    def physical_rx_mask(self) -> int:
        return self._antenna_indexes_to_mask(self.rxs.keys())

    @staticmethod
    def _antenna_indexes_to_mask(indexes: t.Iterable[int]) -> int:
        res = 0
        for idx in indexes:
            res |= 1 << idx
        return res

    def get_correction_scalar(
        self, channel_number: int, az: float, el: float = 0.0, *, profile: Profile
    ) -> complex:
        """Get a correction scalar for the given channel, angles (in radians) and profile

        Uses chebval2d if the profile's table is 3D (az, el correction);
        falls back to chebval (az-only) for a 2D table.
        """
        table = self.antenna_cheb_corr[profile]
        if table.ndim == 3:
            correction_scalar = np.polynomial.chebyshev.chebval2d(
                np.sin(az), np.sin(el), table[:, :, channel_number]
            )
        else:
            # mypy infers a scalar here; it's actually a 1D array (per channel)
            corrections = t.cast(
                "npt.NDArray[np.complex128]",
                np.polynomial.chebyshev.chebval(np.sin(az), table),
            )
            correction_scalar = corrections[channel_number]
        if not isinstance(correction_scalar, complex):
            msg = f"Expected a complex correction scalar, got {type(correction_scalar)}"
            raise TypeError(msg)
        return correction_scalar

    def get_nominal_steering_scalar(self, channel_number: int, az: float, el: float) -> complex:
        """Get a steering scalar for the given channel and angles (in radians)

        The channel number is Tx-major.
        """
        x, y, z = self.channels(tx_mask=0b111, rx_mask=0b1111)[channel_number].position

        argument = (
            x * np.sin(az) + y * np.cos(az) * np.cos(el) + z * np.sin(el) * np.cos(az)
        ) / WAVELENGTH_MM

        return complex(np.exp(-2j * np.pi * argument))

    def get_steering_vector(
        self,
        az: float,
        el: float,
        rx_mask: int,
        tx_mask: int,
        corrected: bool = True,
        *,
        profile: Profile,
    ) -> npt.NDArray[np.complex128]:
        """Get the steering vector for all channels, given angles (in radians) and profile

        The returned steering vector is indexed by channel index (Tx-major)

        See :py:meth:``AntennaArray.get_steering_scalar``.
        """
        steering_array = np.array(
            [
                self.get_nominal_steering_scalar(
                    channel_number,
                    az,
                    el,
                )
                for channel_number in self.channels(tx_mask, rx_mask)
            ]
        )
        if corrected:
            correction_array = np.array(
                [
                    self.get_correction_scalar(
                        channel_number,
                        az,
                        el,
                        profile=profile,
                    )
                    for channel_number in self.channels(tx_mask, rx_mask)
                ]
            )
            correction_weight = np.mean(abs(correction_array))
            correction_array = correction_array / correction_weight
            steering_array = steering_array * correction_array

        std_norm_scaling = np.sqrt((steering_array @ steering_array.conj().T).real)
        steering_array = steering_array / std_norm_scaling
        return steering_array

    def get_steering_vectors(
        self,
        az_angles: npt.NDArray[np.float64],
        el_angles: npt.NDArray[np.float64],
        tx_antenna_mask: int,
        rx_antenna_mask: int,
        *,
        profile: Profile,
    ) -> npt.NDArray[np.complex128]:
        """Calculate steering vectors for all az/el angle combinations, for the given profile.

        Returns an array of shape (num_az, num_el, num_channels).
        """
        num_channels = bin(tx_antenna_mask).count("1") * bin(rx_antenna_mask).count("1")
        steering_vectors = np.zeros(
            shape=(len(az_angles), len(el_angles), num_channels), dtype=np.complex128
        )
        for i, az_deg in enumerate(az_angles):
            for j, el_deg in enumerate(el_angles):
                steering_vectors[i, j, :] = self.get_steering_vector(
                    np.radians(az_deg),
                    np.radians(el_deg),
                    tx_mask=tx_antenna_mask,
                    rx_mask=rx_antenna_mask,
                    profile=profile,
                )
        return steering_vectors

    def channels(self, tx_mask: int, rx_mask: int) -> dict[int, Channel]:
        """Get the channels in this antenna array.

        The keys in the returned dict are the Tx-major channel numbers.
        If the AntennaArray does not contain all antennas masked in by
        the passed masks, those will silently be omitted.

        >>> AntennaArray.AP212.channels(rx_mask=0b1111, tx_mask=0b111)
        {0: Channel(tx=Pos(x=-7.5, y=0.0, z=2.5), rx=Pos(x=-2.5, y=0.0, z=2.5)),
         1: Channel(tx=Pos(x=-7.5, y=0.0, z=2.5), rx=Pos(x=-2.5, y=0.0, z=0.0)),
         2: Channel(tx=Pos(x=-7.5, y=0.0, z=2.5), rx=Pos(x=0.0, y=0.0, z=0.0)),
         3: Channel(tx=Pos(x=-7.5, y=0.0, z=2.5), rx=Pos(x=2.5, y=0.0, z=0.0)),
         4: Channel(tx=Pos(x=7.5, y=0.0, z=2.5), rx=Pos(x=-2.5, y=0.0, z=2.5)),
         5: Channel(tx=Pos(x=7.5, y=0.0, z=2.5), rx=Pos(x=-2.5, y=0.0, z=0.0)),
         6: Channel(tx=Pos(x=7.5, y=0.0, z=2.5), rx=Pos(x=0.0, y=0.0, z=0.0)),
         7: Channel(tx=Pos(x=7.5, y=0.0, z=2.5), rx=Pos(x=2.5, y=0.0, z=0.0)),
         8: Channel(tx=Pos(x=0.0, y=0.0, z=2.5), rx=Pos(x=-2.5, y=0.0, z=2.5)),
         9: Channel(tx=Pos(x=0.0, y=0.0, z=2.5), rx=Pos(x=-2.5, y=0.0, z=0.0)),
         10: Channel(tx=Pos(x=0.0, y=0.0, z=2.5), rx=Pos(x=0.0, y=0.0, z=0.0)),
         11: Channel(tx=Pos(x=0.0, y=0.0, z=2.5), rx=Pos(x=2.5, y=0.0, z=0.0))}
        """
        channel_numbers = ch_conv.get_tx_major_channel_numbers(tx_mask, rx_mask)
        return {
            ch_nbr: Channel(self.txs[tx_idx], self.rxs[rx_idx])
            for ch_nbr, (tx_idx, rx_idx) in channel_numbers.items()
            if tx_idx in self.txs and rx_idx in self.rxs
        }


class AntennaArray(_AntennaArrayData, Enum):  # type: ignore[misc]
    """Antenna arrays of the A2 sensor packages, with antenna positions and channel corrections"""

    def __init__(self, *args: t.Any, **kwargs: t.Any) -> None:
        super().__init__(*args, **kwargs)

    AP212_R2 = (
        {
            0: Pos(-7.5, 0, 2.5),
            1: Pos(7.5, 0, 2.5),
            2: Pos(0, 0, 2.5),
        },
        {
            0: Pos(-2.5, 0, 2.5),
            1: Pos(-2.5, 0, 0),
            2: Pos.origin(),
            3: Pos(2.5, 0, 0),
        },
        _AP212_R2_CHEB_CORR,
    )

    AP212 = AP212_R2

    # Antenna positions are in mm
    # [Tx1         Tx2   Rx0      Tx0 ]
    # [        Rx3 Rx2 Rx1            ]

    @classmethod
    def _missing_(cls, value: object) -> AntennaArray | None:
        if isinstance(value, dict):
            return cls._from_dict(value)
        elif isinstance(value, tuple) and len(value) == 3:
            return cls._from_dict(
                {
                    "txs": value[0],
                    "rxs": value[1],
                    "antenna_cheb_corr": value[2],
                }
            )
        elif member := find_by_name(cls, value):
            return member
        else:
            msg = f"Cannot parse an AntennaArray symbol from {value!r}"
            raise ValueError(msg)

    @classmethod
    def _from_dict(cls, dict_repr: dict[str, t.Any]) -> AntennaArray:
        """This function is used to handle the legacy AntennaArray (now _AntennaArrayData)

        It only looks at the number of Txs to determine if the _AntennaArrayData in question
        is AP212.
        """

        if len(dict_repr.get("txs", [])) == 3:
            return cls.AP212
        else:
            msg = f"Cannot parse an AntennaArray symbol from {dict_repr!r}"
            raise ValueError(msg)

    # Migration-simplifying functions
    @classmethod
    def ap212(cls) -> None:
        msg = f"This function is replaced with the member {cls.AP212.name!r}"
        raise Exception(msg)
