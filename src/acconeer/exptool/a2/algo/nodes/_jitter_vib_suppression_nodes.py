# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

from typing import cast

import numpy as np
import numpy.typing as npt

import acconeer.exptool.a2.algo._utils as utils
from acconeer.exptool import a2


_IIR_FINITE_SUM_EPSILON = 0.001
# constant determining when to drop the rest of the infinite impulse response series

_NEGLIGIBLE_SMOOTH_FACTOR = 1e-6
# smoothing factors at or below this are treated as zero: the IIR has effectively no memory
# and averages a single sample. Also avoids finite_sum_len rounding to 0.


def _iir_weight_power_sum(time_const_s: float, update_rate: float) -> float:
    """``sum(w**2)`` of the normalized weights ``w`` of an exponential filter.

    Returns 1 when the filter is a pass-through.
    """
    exp_smooth_factor = utils.tc_to_sf(tc=time_const_s, fs=update_rate)
    if exp_smooth_factor <= _NEGLIGIBLE_SMOOTH_FACTOR:
        return 1.0
    if exp_smooth_factor >= 1.0:
        msg = (
            f"exp_smooth_factor must be < 1.0, got {exp_smooth_factor!r} "
            f"(time_const_s={time_const_s}, update_rate={update_rate})"
        )
        raise ValueError(msg)
    finite_sum_len = int(np.round(np.log(_IIR_FINITE_SUM_EPSILON) / np.log(exp_smooth_factor)))
    w = (1 - exp_smooth_factor) * exp_smooth_factor ** np.arange(finite_sum_len)
    w /= np.sum(w)
    return float(np.sum(w**2))


def iir_apparent_averaging(time_const_s: float, update_rate: float) -> float:
    """Apparent number of independent samples averaged by an exponential filter.

    The variance of the filtered estimate scales as ``sum(w**2)``, where ``w``
    are the normalized IIR weights, so the apparent averaging is
    ``1 / sum(w**2)``. When ``time_const_s <= 0`` the filter is a pass-through
    and the apparent averaging is 1.

    :param time_const_s: Time constant of the exponential filter in seconds.
    :param update_rate: Rate at which the filter is sampled in Hz.
    """
    return 1.0 / _iir_weight_power_sum(time_const_s=time_const_s, update_rate=update_rate)


def delayed_high_pass_iir_apparent_averaging(
    high_pass_time_const_s: float, time_const_s: float, update_rate: float
) -> float:
    """Apparent averaging of an exponential filter whose snapshots come from a
    ``DelayedExponentialHighPassNode`` fed with white noise.

    The high-pass output ``y[n] = x[n] - background[n - 1]`` is correlated
    from frame to frame: with ``a`` the high-pass smoothing factor its lag
    ``m`` correlation is ``-(1 - a) * a**(m - 1) / 2``. For complex Gaussian
    snapshots the outer products ``|y|**2`` then correlate at lag ``m`` by
    the square of that, and an exponential filter with smoothing factor
    ``b`` averages them with variance inflated by
    ``1 + 2 * sum_m rho_m**2 * b**m = 1 + (1 - a)**2 * b / (2 * (1 - a**2 * b))``.
    The apparent averaging is :func:`iir_apparent_averaging` divided by that
    factor; at ``a = 0`` (frame-to-frame subtraction) the factor is
    ``1 + b / 2``, and it tends to 1 for a long high-pass time constant.

    :param high_pass_time_const_s: Time constant of the delayed high-pass in seconds.
    :param time_const_s: Time constant of the exponential filter in seconds.
    :param update_rate: Rate at which both filters are sampled in Hz.
    """
    a = utils.tc_to_sf(tc=high_pass_time_const_s, fs=update_rate)
    b = utils.tc_to_sf(tc=time_const_s, fs=update_rate)
    inflation = 1.0 + (1.0 - a) ** 2 * b / (2.0 * (1.0 - a**2 * b))
    return iir_apparent_averaging(time_const_s=time_const_s, update_rate=update_rate) / inflation


def covariance_apparent_averaging(
    num_sweeps: float, time_const_s: float, update_rate: float
) -> float:
    """Apparent averaging of snapshots averaged into a per-frame covariance
    matrix that is then smoothed across frames by an exponential filter.

    This is the Wishart degrees of freedom ``N / sum(w**2)`` of the smoothed
    covariance, with ``N`` snapshots per frame and ``w`` the normalized IIR
    weights. If pairs of sweeps are first averaged in IQ, the snapshots are
    the pair means: ``num_sweeps = sweeps_per_frame / 2``, together with
    ``iq_averaging=2`` on :class:`JitterAndVibrationScalingNode`. If the frame
    mean sweep is subtracted from the sweeps first, ``num_sweeps =
    sweeps_per_frame - 1``: the deviations span ``sweeps_per_frame - 1``
    dimensions, so the covariance estimate has the Wishart variance of that
    many snapshots.

    :param num_sweeps: Number of independent snapshots per frame averaged in covariance.
    :param time_const_s: Time constant of the slow-time covariance filter in seconds.
    :param update_rate: Frame update rate in Hz.
    """
    return float(
        num_sweeps / _iir_weight_power_sum(time_const_s=time_const_s, update_rate=update_rate)
    )


class JitterAndVibrationScalingNode:
    """Computes subspace and orthogonal scaling factors for spatial projection.

    Derives per-depth jitter+vibration phase variance from signal amplitude and
    temperature, then converts it to the two scaling factors consumed by
    SubspaceScalingOverCovNode and SubspaceScalingOverSweepsNode.

    The node has assumptions about the upstream signal path:
    - Input is noise-normalized so that thermal noise var = 1.0
    - ``amp_per_depth`` is at single-sweep level and measured along
        the direction the subspace scaling is applied to, see
        ``StaticDirectionAmplitudeNode``. The orthogonal scaling is driven by the
        same static-direction amplitude, so energy outside the static direction
        does not raise it either.
    - The covariance matrix the scaling is applied to averages snapshots with
        ``apparent_avg`` degrees of freedom (Wishart ``nu``), see
        ``covariance_apparent_averaging``.
    - Each snapshot may be the coherent IQ mean of ``iq_averaging`` sweeps. The
        caller must multiply that mean by ``sqrt(iq_averaging)`` so that its
        thermal noise var = 1.0 again; the node does not rescale its input.

    IQ averaging changes the covariance ``Sigma`` the snapshots are drawn from,
    not ``nu``: after the rescale the thermal part is unchanged while the
    jitter/vibration part grows by ``iq_averaging**(1 - jitter_averaging_efficiency)``.
    Covariance averaging sets ``nu``, which enters the subspace scaling as
    ``apparent_avg**(1 - jitter_averaging_efficiency)``. The efficiency was
    fitted for IQ averaging of jitter; applying it to ``apparent_avg`` is an
    assumption, as is applying it to vibration and to the spatially
    uncorrelated (orthogonal) term.
    """

    def __init__(
        self,
        num_points: int,
        num_channels: int,
        profile: a2.Profile,
        vibration_std_um: float,
        apparent_avg: float,
        iq_averaging: float = 1.0,
        spatial_uncorr_jitter_factor: float = 0.1,
        jitter_averaging_efficiency: float = 0.7,
    ) -> None:
        """
        :param num_points: Number of range points.
        :param num_channels: Number of spatial channels.
        :param profile: Sensor profile, used to look up jitter std by temperature.
        :param vibration_std_um: Expected vibration standard deviation in micro metres.
        :param apparent_avg: Apparent averaging at covariance level (Wishart degrees of
            freedom). Build it with ``covariance_apparent_averaging`` or
            ``iir_apparent_averaging``.
        :param iq_averaging: Number of sweeps coherently averaged in IQ into each snapshot of the
            covariance matrix. The caller must multiply the IQ mean by ``sqrt(iq_averaging)``
            so that its thermal noise var = 1.0.
        :param spatial_uncorr_jitter_factor: Suppression weight for jitter that is not spatially
            correlated over time. Experimentally found value 0.1.
        :param jitter_averaging_efficiency: Apparent averaging efficiency for correlated jitter.
            Approximate value found empirically as 0.7.
        """
        if apparent_avg < 1.0:
            msg = f"apparent_avg must be >= 1, got {apparent_avg!r}"
            raise ValueError(msg)
        if iq_averaging < 1.0:
            msg = f"iq_averaging must be >= 1, got {iq_averaging!r}"
            raise ValueError(msg)
        self.num_points = num_points
        self.num_channels = num_channels
        self.profile = profile
        self.vibration_std_um = vibration_std_um
        self._spatial_uncorr_jitter_factor = spatial_uncorr_jitter_factor
        self._jitter_averaging_efficiency = jitter_averaging_efficiency

        self._vibration_std_rad = 2.0 * np.pi * vibration_std_um * 1e-6 / utils.BASE_STEP_LENGTH_M
        self._apparent_avg = float(apparent_avg)
        self._iq_averaging = float(iq_averaging)

    def execute(
        self,
        amp_per_depth: npt.NDArray[np.float64],
        temperature: float,
    ) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
        """
        :param amp_per_depth: Signal amplitude along the static direction per depth
            point, shape (num_points,).
        :param temperature: Current temperature in degrees Celsius.
        :returns: Tuple of (subspace_scaling, orthogonal_scaling), each shape (num_points,).
        """
        if amp_per_depth.shape != (self.num_points,):
            msg = f"amp_per_depth: expected shape {(self.num_points,)}, got {amp_per_depth.shape}"
            raise ValueError(msg)

        profile_jitter = utils.JITTER_STD_DEG[self.profile]
        jitter_std_deg = np.interp(
            temperature, list(profile_jitter.keys()), list(profile_jitter.values())
        )
        jitter_std_rad = np.deg2rad(jitter_std_deg)

        signal_power = amp_per_depth**2
        jitter_var = signal_power * (1.0 - np.exp(-(jitter_std_rad**2)))
        vibration_var = signal_power * (1.0 - np.exp(-(self._vibration_std_rad**2)))
        combined_var = (jitter_var + vibration_var) * self._iq_averaging ** (
            1 - self._jitter_averaging_efficiency
        )

        subspace_scaling = 1.0 / np.sqrt(
            1.0
            + combined_var
            * self.num_channels
            * self._apparent_avg ** (1 - self._jitter_averaging_efficiency)
        )
        orthogonal_scaling = 1.0 / np.sqrt(1.0 + combined_var * self._spatial_uncorr_jitter_factor)

        return cast(npt.NDArray[np.float64], subspace_scaling), cast(
            npt.NDArray[np.float64], orthogonal_scaling
        )
