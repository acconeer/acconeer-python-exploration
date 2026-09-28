# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import attrs
import numpy as np
import numpy.typing as npt

import acconeer.exptool.a2.algo._utils as utils
from acconeer.exptool import a2
from acconeer.exptool.a2._core.channel_convention import get_subset_channel_indexes
from acconeer.exptool.a2.algo._detection_geometry import (
    DetectionVolume,
    SensorInstallation,
)
from acconeer.exptool.a2.algo._utils import get_effective_frame_rate, tc_to_sf
from acconeer.exptool.a2.algo.nodes._beamforming_nodes import (
    BatchConventionalBeamformNode,
    CaponBeamformNode,
    RobustCaponBeamformNode,
)
from acconeer.exptool.a2.algo.nodes._cfar_nodes import CFAR2DThresholdNode
from acconeer.exptool.a2.algo.nodes._filter_nodes import (
    ExponentialHighPassNode,
    ExponentialLowPassNode,
)
from acconeer.exptool.a2.algo.nodes._heatmap_peak_nodes import (
    Peak3DCart,
    Peak3DCartBoxFilterNode,
    Peak3DCartXYNMSNode,
    Peak3DSphericalToCartesianNode,
    PeakFuseNode,
    PeakToListNode,
)
from acconeer.exptool.a2.algo.nodes._jitter_vib_suppression_nodes import (
    JitterAndVibrationScalingNode,
    covariance_apparent_averaging,
)
from acconeer.exptool.a2.algo.nodes._peak_finding_nodes import LocalMaxima2DNode
from acconeer.exptool.a2.algo.nodes._peak_interpolation_nodes import (
    Interpolation2DNode,
    Peak1DInterpolationNode,
)
from acconeer.exptool.a2.algo.nodes._simple_nodes import (
    ArgmaxNode,
    CovarianceNode,
    CovarianceSubarrayNode,
    MeanNode,
    NaNGuardNode,
    ReshapeNode,
    SubtractNode,
)
from acconeer.exptool.a2.algo.nodes._subspace_scaling_nodes import (
    StaticDirectionAmplitudeNode,
    SubspaceScalingOverCovNode,
)
from acconeer.exptool.a2.algo.noise_normalization import (
    NoiseNormalizationRecording,
    NoiseNormalizationResultProcessor,
)

from .config import BeamformingMethod, MotionDetectionConfig


_AZ_RX_DROP_MASK = 0b0001  # Drop Rx0 (z=2.5) to obtain a single virtual-elevation row


@attrs.frozen(kw_only=True)
class MotionDetectionResult:
    peaks: list[Peak3DCart]
    """Refined peak locations from the heatmap."""

    heatmap: npt.NDArray[np.float64]
    """The (D, Az) Capon heatmap formed from the azimuth sub-array.

    The dedicated azimuth sub-array (Rx0 dropped) has a single virtual
    elevation row, so the heatmap is 2D and provided directly to
    consumers for plotting and analysis.
    """

    threshold_map: npt.NDArray[np.float64]
    """The CFAR threshold map. Provided for plotting and analysis purposes."""

    el_spectra: npt.NDArray[np.float64]
    """Per-peak elevation spectrum of shape ``(N_peaks, El)``.

    Each row is the conventional beamform output along the elevation grid
    for a single 2D peak, computed from the full-channel covariance at the
    peak's distance bin and the elevation steering vectors at the peak's
    az index.
    """


class MotionDetectionProcessor:
    def __init__(
        self,
        session_config: a2.SessionConfig,
        processor_config: MotionDetectionConfig,
        sensor_installation: SensorInstallation,
        detection_volume: DetectionVolume,
        noise_norm_recording: NoiseNormalizationRecording | None,
    ):
        self.processor_config = processor_config
        self.session_config = session_config
        self.sensor_installation = sensor_installation
        self.detection_volume = detection_volume

        frame_rate = get_effective_frame_rate(session_config)
        if frame_rate is None:
            msg = "frame_rate or update_rate must be specified"
            raise ValueError(msg)
        self._frame_rate = frame_rate

        # Build a single virtual view representing the union of all subsweeps.
        # Downstream code reads tx/rx mask, profile, step_length, num_points and
        # num_channels off this view, which requires those fields to be identical
        # across all subsweeps and the subsweeps to be contiguous -- both enforced
        # by ConcatenatedSubsweepView itself.
        subsweeps = self.session_config.sensor_config.subsweeps
        try:
            self._concat_subsweep_config = utils.ConcatenatedSubsweepView.from_subsweeps(subsweeps)
        except ValueError as e:
            raise RuntimeError(str(e)) from e

        self._az_angles = processor_config.az_angles(detection_volume)
        self._el_angles = processor_config.el_angles(detection_volume)
        self._az_span = processor_config.az_span(detection_volume)

        if noise_norm_recording is None:
            msg = "Missing noise normalization recording."
            raise ValueError(msg)
        self._noise_normalization_processor = NoiseNormalizationResultProcessor(
            self.session_config,
            noise_norm_recording,
        )

        num_points = self._concat_subsweep_config.num_points
        num_channels = self._concat_subsweep_config.num_channels

        temporal_lp = np.float64(
            tc_to_sf(processor_config.high_pass_filter_time_constant_s, self._frame_rate)
        )
        spatial_lp = np.float64(
            tc_to_sf(processor_config.spatial_high_pass_filter_time_constant_s, self._frame_rate)
        )
        covar_lp = np.float64(
            tc_to_sf(processor_config.covariance_matrix_time_constant_s, self._frame_rate)
        )

        # --- IQ Preprocessing ---
        self._reshape_node: ReshapeNode[np.complex128] = ReshapeNode(
            target_shape=(-1, num_points, num_channels)
        )
        self._mean_node: MeanNode[np.complex128] = MeanNode(axis=0)
        self._temporal_env_filter: ExponentialHighPassNode[np.complex128] = (
            ExponentialHighPassNode(
                input_shape=(num_points, num_channels),
                lp_constant=temporal_lp,
                dtype=np.complex128,
            )
        )
        self._spatial_env_filter: ExponentialLowPassNode[np.complex128] = ExponentialLowPassNode(
            input_shape=(num_points, num_channels),
            lp_constant=spatial_lp,
            dtype=np.complex128,
        )
        self._static_dir_amp_node: StaticDirectionAmplitudeNode = StaticDirectionAmplitudeNode()
        self._amp_filter: ExponentialLowPassNode[np.float64] = ExponentialLowPassNode(
            input_shape=(num_points,),
            lp_constant=covar_lp,
            dtype=np.float64,
        )
        apparent_avg = covariance_apparent_averaging(
            num_sweeps=session_config.sensor_config.sweeps_per_frame,
            time_const_s=processor_config.covariance_matrix_time_constant_s,
            update_rate=self._frame_rate,
        )
        self._jitter_node = JitterAndVibrationScalingNode(
            num_points=num_points,
            num_channels=num_channels,
            profile=self._concat_subsweep_config.profile,
            vibration_std_um=processor_config.vibration_std_um,
            apparent_avg=apparent_avg,
            spatial_uncorr_jitter_factor=processor_config.spatial_uncorr_jitter_factor,
            jitter_averaging_efficiency=processor_config.jitter_averaging_efficiency,
        )
        self._spatial_proj_node = SubspaceScalingOverCovNode(
            num_points=num_points,
            num_channels=num_channels,
        )
        self._subtract_node: SubtractNode[np.complex128] = SubtractNode()
        self._covariance_node = CovarianceNode(axis=2)
        self._sweep_mean_node: MeanNode[np.complex128] = MeanNode(axis=0)
        self._covariance_filter: ExponentialLowPassNode[np.complex128] = ExponentialLowPassNode(
            input_shape=(num_points, num_channels, num_channels),
            lp_constant=covar_lp,
            dtype=np.complex128,
        )

        # --- Heatmap ---
        # The az sub-array drops Rx0 (z=2.5) so the remaining Rx all share
        # z=0; combined with the Tx row at z=2.5 the virtual array has a
        # single elevation row -- ideal for the 2D (D, Az) Capon heatmap.
        # Dropping Rx0 can leave zero active receivers (if Rx0 was the only
        # one enabled), so that specific case is checked explicitly for a clearer
        # error message.
        #
        # Elevation refinement uses all available channels (no drop): it
        # isn't tied to a specific coplanar sub-array, so whatever Tx/Rx mask
        # the caller configured is used as-is.
        tx_mask = self._concat_subsweep_config.tx_antenna_mask
        rx_mask = self._concat_subsweep_config.rx_antenna_mask
        az_rx_mask = rx_mask & ~_AZ_RX_DROP_MASK
        az_virtual_channels = bin(tx_mask).count("1") * bin(az_rx_mask).count("1")
        if az_virtual_channels < 1:
            msg = "Az sub-array has no virtual channels: at least one of Rx1, Rx2, Rx3 needs to be selected."
            raise ValueError(msg)
        self._az_channel_indices = get_subset_channel_indexes(
            tx_mask_super=tx_mask,
            rx_mask_super=rx_mask,
            tx_mask_sub=tx_mask,
            rx_mask_sub=az_rx_mask,
        )

        # Az sub-array has a single virtual el row, but the existing Capon and
        # RobustCapon beamformers assume an (Az, El, C) steering layout, so
        # keep the el axis of length 1 here. The resulting heatmap is squeezed
        # back to (D, Az) in ``process``.
        self._az_steering: npt.NDArray[np.complex128] = (
            processor_config.antenna_array.get_steering_vectors(
                self._az_angles,
                np.array([0.0]),
                tx_mask,
                az_rx_mask,
                profile=self._concat_subsweep_config.profile,
            )
        )
        self._el_steering: npt.NDArray[np.complex128] = (
            processor_config.antenna_array.get_steering_vectors(
                self._az_angles,
                self._el_angles,
                tx_mask,
                rx_mask,
                profile=self._concat_subsweep_config.profile,
            )
        )

        self._az_cov_subarray_node: CovarianceSubarrayNode[np.complex128] = CovarianceSubarrayNode(
            self._az_channel_indices,
        )

        beamformer: CaponBeamformNode | RobustCaponBeamformNode
        method = processor_config.beamforming_method
        if method is BeamformingMethod.CAPON:
            beamformer = CaponBeamformNode(steering_vectors=self._az_steering)
        elif method is BeamformingMethod.ROBUST_CAPON:
            beamformer = RobustCaponBeamformNode(
                steering_vectors=self._az_steering,
                steering_vector_epsilon=processor_config.robust_capon_epsilon,
            )
        else:
            msg = f"Unsupported beamforming method for motion detection: {method}"
            raise ValueError(msg)
        self._az_beamformer = beamformer

        self._el_beamformer = BatchConventionalBeamformNode()

        # --- Heatmap Processing ---
        self._spherical_to_cart_node = Peak3DSphericalToCartesianNode(
            sensor_installation.mount_rotation
        )
        self._box_filter_node = Peak3DCartBoxFilterNode(
            x_bounds_m=processor_config.effective_x_bounds_m(detection_volume),
            y_bounds_m=processor_config.effective_y_bounds_m(detection_volume),
            z_bounds_m=processor_config.effective_z_bounds_m(
                sensor_installation, detection_volume
            ),
        )
        self._distances_m = utils.get_distances_from_config(self._concat_subsweep_config)
        profile = self._concat_subsweep_config.profile
        step_length_m = self._concat_subsweep_config.step_length * utils.BASE_STEP_LENGTH_M
        num_points = len(self._distances_m)

        self._heatmap_nan_guard: NaNGuardNode[np.float64] = NaNGuardNode(
            fill_value=np.float64(0.0)
        )

        guard_radii, ref_radii = processor_config.get_cfar_radii(
            detection_volume, profile, step_length_m, num_points
        )
        self._cfar_node = CFAR2DThresholdNode(
            input_shape=(num_points, processor_config.num_az_angles(detection_volume)),
            guard_radii=guard_radii,
            ref_radii=ref_radii,
            kernel_type=processor_config.cfar_kernel_type,
            aggregate_method=processor_config.cfar_aggregate_method,
            theoretical_fpr=processor_config.cfar_theoretical_fpr,
            fixed_threshold=processor_config.cfar_fixed_threshold,
            side_lobe_compensation_dB=(None, processor_config.cfar_side_lobe_compensation_db),
        )

        n_dist, n_az = processor_config.get_peak_finding_radii(
            detection_volume, profile, step_length_m, num_points
        )
        self._local_maxima_2d_node = LocalMaxima2DNode(radii=(n_dist, n_az))
        self._interpolation_2d_node = Interpolation2DNode(
            axis0_grid=self._distances_m,
            axis1_grid=self._az_angles,
            method=processor_config.peak_interpolation_az_dist_method,
            radius=(n_dist, n_az),
        )
        self._peak_index_node = PeakToListNode(field="index")
        self._el_argmax_node: ArgmaxNode[np.float64] = ArgmaxNode(axis=1)
        self._el_interpolation_node = Peak1DInterpolationNode(
            axis_grid=self._el_angles,
            radius=processor_config.n_el_interpolation(detection_volume),
        )
        self._peak_fuse_node = PeakFuseNode()
        self._nms_node = Peak3DCartXYNMSNode(
            min_dist_separation_m=processor_config.peak_min_dist_separation_m,
        )

    def process(self, result: a2.Result) -> MotionDetectionResult:
        norm_result = self._noise_normalization_processor.process(result=result)

        # --- IQ Preprocessing ---
        frame: npt.NDArray[np.complex128] = self._reshape_node.execute(norm_result.frame)
        mean_sweep: npt.NDArray[np.complex128] = self._mean_node.execute(frame)  # type: ignore[assignment]

        highpass_mean_sweep: npt.NDArray[np.complex128] = self._temporal_env_filter.execute(
            mean_sweep
        )

        mean_sweep_background: npt.NDArray[np.complex128] = self._subtract_node.execute(
            mean_sweep, highpass_mean_sweep
        )
        frame_hp: npt.NDArray[np.complex128] = self._subtract_node.execute(
            frame, mean_sweep_background
        )
        cov_per_sweep = self._covariance_node.execute(frame_hp)
        mean_cov: npt.NDArray[np.complex128] = self._sweep_mean_node.execute(cov_per_sweep)  # type: ignore[assignment]

        spatial_static_env = self._spatial_env_filter.execute(mean_sweep)
        static_dir_amp = self._static_dir_amp_node.execute(
            static=spatial_static_env, sweep=mean_sweep
        )
        filtered_static_dir_amp: npt.NDArray[np.float64] = self._amp_filter.execute(static_dir_amp)
        subspace_scaling, orthogonal_scaling = self._jitter_node.execute(
            amp_per_depth=filtered_static_dir_amp, temperature=norm_result.temperature
        )
        mean_cov = self._spatial_proj_node.execute(
            mean_cov, spatial_static_env, subspace_scaling, orthogonal_scaling
        )

        filtered_cov = self._covariance_filter.execute(mean_cov)

        # --- Heatmap (Az sub-array Capon) ---
        az_cov = self._az_cov_subarray_node.execute(filtered_cov)
        # Beamformer output is (D, Az, 1) due to the singleton el dim in the
        # steering matrix; squeeze it back to (D, Az).
        heatmap: npt.NDArray[np.float64] = self._az_beamformer.execute(az_cov).squeeze(axis=2)
        heatmap = self._heatmap_nan_guard.execute(heatmap)

        # --- 2D peak finding on the (D, Az) heatmap ---
        threshold_map = self._cfar_node.execute(heatmap)
        candidates = self._local_maxima_2d_node.execute(
            data=heatmap,
            threshold=threshold_map,
        )
        peaks_2d = self._interpolation_2d_node.execute(
            data=heatmap,
            indices=candidates,
        )

        # --- Per-peak elevation refinement via all available channels ---
        peak_2d_indices = np.asarray(
            self._peak_index_node.execute(peaks_2d), dtype=np.intp
        ).reshape(-1, 2)
        peak_d_idx = peak_2d_indices[:, 0]
        peak_az_idx = peak_2d_indices[:, 1]
        el_covs_at_peaks = filtered_cov[peak_d_idx]
        el_sv_at_peaks = self._el_steering[peak_az_idx]
        el_spectra = self._el_beamformer.execute(el_covs_at_peaks, el_sv_at_peaks)

        el_argmax: npt.NDArray[np.intp] = self._el_argmax_node.execute(el_spectra)  # type: ignore[assignment]
        peaks_1d = self._el_interpolation_node.execute(el_spectra, el_argmax)
        raw_peaks = self._peak_fuse_node.execute(peaks_1d, peaks_2d)
        peaks_cart = self._spherical_to_cart_node.execute(raw_peaks)
        peaks_cart = self._box_filter_node.execute(peaks_cart)
        peaks = self._nms_node.execute(peaks_cart)

        return MotionDetectionResult(
            peaks=peaks,
            heatmap=heatmap,
            threshold_map=threshold_map,
            el_spectra=el_spectra,
        )
