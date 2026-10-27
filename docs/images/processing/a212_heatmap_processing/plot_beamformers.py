# Copyright (c) Acconeer AB, 2026
# All rights reserved
"""Replay an .h5 record through all heatmap beamformers and render plots.

Produces one D-Az heatmap + 1D marginals figure and one El-spectrum figure per
beamformer (conventional, capon, robust_capon, coherent), plus two comparison
figures overlaying all beamformers (Az and El 1D cuts at the strongest peak
from the conventional beamformer).

All figures are written to the ``figures/`` subfolder next to this script.

Example:
    python plot_beamformers.py --input-file data.h5 --frame-index 100
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Optional

import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt

from acconeer.exptool import a2
from acconeer.exptool.a2._core.recording.replaying_client import ReplayingClient
from acconeer.exptool.a2.algo.heatmap import capon as capon_pkg
from acconeer.exptool.a2.algo.heatmap import coherent as coherent_pkg
from acconeer.exptool.a2.algo.heatmap import conventional as conventional_pkg
from acconeer.exptool.a2.algo.heatmap import robust_capon as robust_capon_pkg
from acconeer.exptool.a2.algo.heatmap.processor_common import (
    HeatmapProcessorCommon,
    ProcessorResultCommon,
)
from acconeer.exptool.a2.algo.noise_normalization import (
    NoiseNormalizationResultProcessor,
    load_noise_normalization_recording,
)


BASE_STEP_LENGTH_M = 2.5e-3
DEGREE_SYMBOL = "°"

AZ_RANGE = (-60.0, 60.0)
EL_RANGE = (-30.0, 30.0)
NUM_AZ = 200  # 1° spacing
NUM_EL = 61  # 1° spacing

PEAK_COLORS = ("#ff3b30", "#ff9500", "#ffcc00")  # red, orange, yellow
NUM_PEAKS = 3

PRETTY_NAME = {
    "conventional": "Conventional",
    "capon": "Capon",
    "robust_capon": "Robust Capon",
    "coherent": "Coherent",
}
NMS_AZ_HALF_DEG = 15
NMS_D_HALF_BINS = 10

ANTENNA_ARRAY = a2.AntennaArray.AP212


@dataclass
class BeamformerSpec:
    name: str
    processor: HeatmapProcessorCommon[Any]
    is_coherent: bool


# ------------------------- replay / processing -------------------------


def _make_processors(
    subsweep_config: a2.SubsweepConfig, update_rate: float
) -> list[BeamformerSpec]:
    conv_config = conventional_pkg.HeatmapConfig(
        antenna_array=ANTENNA_ARRAY,
        heatmap_mode=conventional_pkg.HeatmapConfig.HeatmapMode.MOVEMENT,
        covariance_matrix_time_constant_s=0.5,
        high_pass_filter_time_constant_s=1.0,
        az_angle_range=AZ_RANGE,
        el_angle_range=EL_RANGE,
        num_az_angles=NUM_AZ,
        num_el_angles=NUM_EL,
        normalized_heat_cutoff=0.0,
        max_2d_heat=None,
        log_scale_output=False,
    )
    capon_config = capon_pkg.HeatmapConfig(
        antenna_array=ANTENNA_ARRAY,
        covariance_matrix_time_constant_s=0.5,
        high_pass_filter_time_constant_s=1.0,
        az_angle_range=AZ_RANGE,
        el_angle_range=EL_RANGE,
        num_az_angles=NUM_AZ,
        num_el_angles=NUM_EL,
        normalized_heat_cutoff=0.0,
        max_2d_heat=None,
        log_scale_output=False,
    )
    robust_capon_config = robust_capon_pkg.HeatmapConfig(
        antenna_array=ANTENNA_ARRAY,
        covariance_matrix_time_constant_s=0.5,
        high_pass_filter_time_constant_s=1.0,
        steering_vector_epsilon=0.02,
        az_angle_range=AZ_RANGE,
        el_angle_range=EL_RANGE,
        num_az_angles=NUM_AZ,
        num_el_angles=NUM_EL,
        normalized_heat_cutoff=0.0,
        max_2d_heat=None,
        log_scale_output=False,
    )
    coherent_config = coherent_pkg.HeatmapConfig(
        antenna_array=ANTENNA_ARRAY,
        heatmap_mode=coherent_pkg.HeatmapConfig.HeatmapMode.MOVEMENT,
        high_pass_filter_time_constant_s=1.0,
        az_angle_range=AZ_RANGE,
        el_angle_range=EL_RANGE,
        num_az_angles=NUM_AZ,
        num_el_angles=NUM_EL,
        normalized_heat_cutoff=0.0,
        max_2d_heat=None,
        log_scale_output=False,
        display_mode=coherent_pkg.HeatmapConfig.DisplayMode.ABSOLUTE,
    )
    return [
        BeamformerSpec(
            "conventional",
            conventional_pkg.HeatmapProcessor(subsweep_config, conv_config, update_rate),
            is_coherent=False,
        ),
        BeamformerSpec(
            "capon",
            capon_pkg.HeatmapProcessor(subsweep_config, capon_config, update_rate),
            is_coherent=False,
        ),
        BeamformerSpec(
            "robust_capon",
            robust_capon_pkg.HeatmapProcessor(subsweep_config, robust_capon_config, update_rate),
            is_coherent=False,
        ),
        BeamformerSpec(
            "coherent",
            coherent_pkg.HeatmapProcessor(subsweep_config, coherent_config, update_rate),
            is_coherent=True,
        ),
    ]


def _resolve_update_rate(record: a2.H5Record) -> float:
    session_config = record.session_config
    if session_config.update_rate is not None:
        return float(session_config.update_rate)
    ticks_per_second = record.server_info.ticks_per_second
    tick_period = record.session(0).tick_period
    if tick_period > 0.0:
        return float(ticks_per_second) / float(tick_period)
    msg = (
        "Could not determine update rate from the record: "
        "session_config.update_rate is None and session(0).tick_period is non-positive."
    )
    raise RuntimeError(msg)


def _iter_nn_results(
    record: a2.H5Record, noise_norm_processor: Optional[NoiseNormalizationResultProcessor]
) -> Iterator[a2.Result]:
    client = ReplayingClient(record=record, realtime_replay=False)
    client.setup_session(record.session_config)
    client.start_session()
    try:
        while True:
            try:
                result = client.get_next(format=a2.Client.ResultFormat.SOLE)
            except StopIteration:
                break
            yield (
                noise_norm_processor.process(result)
                if noise_norm_processor is not None
                else result
            )
    finally:
        client.stop_session()


def _replay_and_collect(
    record: a2.H5Record, frame_index: int
) -> tuple[list[tuple[str, bool, ProcessorResultCommon]], a2.SubsweepConfig]:
    """Replay the entire record through every beamformer and return the result
    for ``frame_index`` per beamformer.
    """
    algo_group = record.file.get("algo")
    noise_recording = (
        load_noise_normalization_recording(algo_group) if algo_group is not None else None
    )
    noise_norm_processor = (
        NoiseNormalizationResultProcessor(
            session_config=record.session_config, noise_recording=noise_recording
        )
        if noise_recording is not None
        else None
    )
    if noise_norm_processor is None:
        print("[plot_beamformers] no noise normalization recording found in input file")

    subsweep_config = record.session_config.sensor_config.subsweep
    update_rate = _resolve_update_rate(record)
    specs = _make_processors(subsweep_config, update_rate)

    captured: list[Optional[ProcessorResultCommon]] = [None] * len(specs)
    frames_seen = 0
    for i, nn_result in enumerate(_iter_nn_results(record, noise_norm_processor)):
        frames_seen = i + 1
        for j, spec in enumerate(specs):
            result = spec.processor.process(nn_result)
            if i == frame_index:
                captured[j] = result
        if i >= frame_index:
            break

    missing = [specs[j].name for j, r in enumerate(captured) if r is None]
    if missing:
        msg = (
            f"frame_index={frame_index} not reached for beamformers: {missing}. "
            f"The record only contains {frames_seen} frames."
        )
        raise RuntimeError(msg)

    return (
        [(spec.name, spec.is_coherent, r) for spec, r in zip(specs, captured) if r is not None],
        subsweep_config,
    )


# ------------------------- peak finding -------------------------


def _find_top_peaks(
    heatmap_2d: npt.NDArray[np.float64],
    distances_m: npt.NDArray[np.float64],
    az_angles: npt.NDArray[np.float64],
    num_peaks: int,
) -> list[tuple[int, int]]:
    """Return up to ``num_peaks`` ``(d_idx, az_idx)`` peaks via simple NMS."""
    work = np.nan_to_num(heatmap_2d.copy(), nan=-np.inf)
    az_step_deg = float(az_angles[1] - az_angles[0]) if len(az_angles) > 1 else 1.0
    az_half = max(1, int(round(NMS_AZ_HALF_DEG / az_step_deg)))
    d_half = NMS_D_HALF_BINS

    peaks: list[tuple[int, int]] = []
    for _ in range(num_peaks):
        if not np.isfinite(work).any():
            break
        flat_idx = int(np.argmax(work))
        d_idx, az_idx = int(flat_idx // work.shape[1]), int(flat_idx % work.shape[1])
        if not np.isfinite(work[d_idx, az_idx]):
            break
        peaks.append((d_idx, az_idx))
        d_lo, d_hi = max(0, d_idx - d_half), min(work.shape[0], d_idx + d_half + 1)
        a_lo, a_hi = max(0, az_idx - az_half), min(work.shape[1], az_idx + az_half + 1)
        work[d_lo:d_hi, a_lo:a_hi] = -np.inf
    return peaks


# ------------------------- plotting -------------------------


def _to_display(values: npt.NDArray[np.float64], color_scale: str) -> npt.NDArray[np.float64]:
    if color_scale == "db":
        safe = np.maximum(values, np.finfo(np.float64).tiny)
        return np.asarray(10.0 * np.log10(safe), dtype=np.float64)
    return values


def _cbar_label(color_scale: str) -> str:
    return "[dB]" if color_scale == "db" else "[lin]"


def _distances_m(
    heatmap: npt.NDArray[np.float64], subsweep_config: a2.SubsweepConfig
) -> npt.NDArray[np.float64]:
    start_m = subsweep_config.start_point * BASE_STEP_LENGTH_M
    step_m = subsweep_config.step_length * BASE_STEP_LENGTH_M
    num_d = heatmap.shape[0]
    return start_m + step_m * np.arange(num_d)


def _plot_daz_with_marginals(
    name: str,
    heatmap_2d: npt.NDArray[np.float64],
    distances_m: npt.NDArray[np.float64],
    az_angles: npt.NDArray[np.float64],
    peaks: list[tuple[int, int]],
    output_path: Path,
    color_scale: str,
) -> None:
    image = _to_display(heatmap_2d, color_scale)

    fig = plt.figure(figsize=(8, 7))
    # Give the colorbar its own gridspec column so the bottom Az plot stays
    # aligned with the heatmap's Az axis (and not with heatmap + colorbar).
    gs = fig.add_gridspec(
        2,
        3,
        width_ratios=(1.0, 4.0, 0.18),
        height_ratios=(4.0, 1.0),
        wspace=0.05,
        hspace=0.05,
    )
    ax_d = fig.add_subplot(gs[0, 0])
    ax_heat = fig.add_subplot(gs[0, 1])
    ax_az = fig.add_subplot(gs[1, 1])
    cax = fig.add_subplot(gs[0, 2])

    extent = (az_angles[0], az_angles[-1], distances_m[-1], distances_m[0])
    im = ax_heat.imshow(image, aspect="auto", cmap="viridis", origin="upper", extent=extent)
    ax_heat.tick_params(axis="y", labelleft=False)
    ax_heat.tick_params(axis="x", labelbottom=False)
    fig.colorbar(im, cax=cax, label=_cbar_label(color_scale))

    for (d_idx, az_idx), color in zip(peaks, PEAK_COLORS):
        ax_heat.scatter(
            az_angles[az_idx],
            distances_m[d_idx],
            s=80,
            facecolors="none",
            edgecolors=color,
            linewidths=2.0,
            zorder=5,
        )
        ax_heat.axhline(distances_m[d_idx], color=color, linestyle="--", linewidth=1.0, alpha=0.8)
        ax_heat.axvline(az_angles[az_idx], color=color, linestyle="--", linewidth=1.0, alpha=0.8)

    # Bottom marginal (Az axis): Az spectrum at each peak's distance
    for (d_idx, az_idx), color in zip(peaks, PEAK_COLORS):
        spectrum = _to_display(heatmap_2d[d_idx, :], color_scale)
        ax_az.plot(az_angles, spectrum, color=color, linewidth=1.4)
        ax_az.scatter([az_angles[az_idx]], [spectrum[az_idx]], color=color, s=40, zorder=5)
        ax_az.axvline(az_angles[az_idx], color=color, linestyle="--", linewidth=1.0, alpha=0.8)
    ax_az.set_xlim(az_angles[0], az_angles[-1])
    ax_az.set_xlabel(f"Az angle [{DEGREE_SYMBOL}]")
    ax_az.set_ylabel(_cbar_label(color_scale))
    ax_az.grid(True, alpha=0.3)

    # Left marginal (D axis): D spectrum at each peak's az; x axis (heat) increases to the right
    for (d_idx, az_idx), color in zip(peaks, PEAK_COLORS):
        spectrum = _to_display(heatmap_2d[:, az_idx], color_scale)
        ax_d.plot(spectrum, distances_m, color=color, linewidth=1.4)
        ax_d.scatter([spectrum[d_idx]], [distances_m[d_idx]], color=color, s=40, zorder=5)
        ax_d.axhline(distances_m[d_idx], color=color, linestyle="--", linewidth=1.0, alpha=0.8)
    ax_d.set_ylim(distances_m[-1], distances_m[0])
    ax_d.set_ylabel("Distance [m]")
    ax_d.set_xlabel(_cbar_label(color_scale))
    ax_d.invert_xaxis()
    ax_d.grid(True, alpha=0.3)

    fig.suptitle(f"{PRETTY_NAME.get(name, name)} D-Az Heatmap")
    fig.savefig(output_path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def _plot_el_spectrum(
    name: str,
    heatmap_3d: npt.NDArray[np.float64],
    el_angles: npt.NDArray[np.float64],
    peaks: list[tuple[int, int]],
    output_path: Path,
    color_scale: str,
) -> None:
    fig, ax = plt.subplots(figsize=(7, 4))
    for (d_idx, az_idx), color in zip(peaks, PEAK_COLORS):
        spectrum = _to_display(heatmap_3d[d_idx, az_idx, :], color_scale)
        ax.plot(el_angles, spectrum, color=color, linewidth=1.6)
        peak_el_idx = int(np.argmax(spectrum))
        ax.scatter([el_angles[peak_el_idx]], [spectrum[peak_el_idx]], color=color, s=40, zorder=5)
    ax.set_xlabel(f"El angle [{DEGREE_SYMBOL}]")
    ax.set_ylabel(_cbar_label(color_scale))
    ax.set_xlim(el_angles[0], el_angles[-1])
    ax.grid(True, alpha=0.3)
    ax.set_title(f"{PRETTY_NAME.get(name, name)} El Spectrum")
    fig.tight_layout()
    fig.savefig(output_path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def _plot_comparison_az(
    results: list[tuple[str, npt.NDArray[np.float64]]],
    az_angles: npt.NDArray[np.float64],
    peak_d_idx: int,
    peak_el_idx: int,
    output_path: Path,
    color_scale: str,
) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for name, heatmap_3d in results:
        cut = _to_display(heatmap_3d[peak_d_idx, :, peak_el_idx], color_scale)
        ax.plot(az_angles, cut, linewidth=1.5, label=PRETTY_NAME.get(name, name))
    ax.set_xlabel(f"Az angle [{DEGREE_SYMBOL}]")
    ax.set_ylabel(_cbar_label(color_scale))
    ax.set_xlim(az_angles[0], az_angles[-1])
    ax.grid(True, alpha=0.3)
    ax.legend()
    ax.set_title("Beamformer Comparison — Az Spectrum")
    fig.tight_layout()
    fig.savefig(output_path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def _plot_comparison_el(
    results: list[tuple[str, npt.NDArray[np.float64]]],
    el_angles: npt.NDArray[np.float64],
    peak_d_idx: int,
    peak_az_idx: int,
    output_path: Path,
    color_scale: str,
) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for name, heatmap_3d in results:
        cut = _to_display(heatmap_3d[peak_d_idx, peak_az_idx, :], color_scale)
        ax.plot(el_angles, cut, linewidth=1.5, label=PRETTY_NAME.get(name, name))
    ax.set_xlabel(f"El angle [{DEGREE_SYMBOL}]")
    ax.set_ylabel(_cbar_label(color_scale))
    ax.set_xlim(el_angles[0], el_angles[-1])
    ax.grid(True, alpha=0.3)
    ax.legend()
    ax.set_title("Beamformer Comparison — El Spectrum")
    fig.tight_layout()
    fig.savefig(output_path, dpi=120, bbox_inches="tight")
    plt.close(fig)


# ------------------------- main -------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-file",
        default=str(Path(__file__).parent / "3_corner_ref.h5"),
        help="path to .h5 record to replay (defaults to 3_corner_ref.h5 next to this script)",
    )
    parser.add_argument(
        "--frame-index",
        type=int,
        default=100,
        help="frame index in the recording whose results are plotted",
    )
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).parent / "figures"),
        help="directory to write figures to (created if needed)",
    )
    parser.add_argument(
        "--color-scale",
        choices=("linear", "db"),
        default="db",
        help="heatmap / 1D y-axis scale",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with a2.open_record(args.input_file) as record:
        captured, subsweep_config = _replay_and_collect(record, args.frame_index)

    captured_heat: list[tuple[str, bool, ProcessorResultCommon, npt.NDArray[np.float64]]] = []
    for name, is_coherent, result in captured:
        if result.heatmap is None:
            msg = f"Beamformer {name} produced no heatmap for frame {args.frame_index}."
            raise RuntimeError(msg)
        captured_heat.append((name, is_coherent, result, result.heatmap))

    az_angles = captured_heat[0][2].heatmap_config.az_angles
    el_angles = captured_heat[0][2].heatmap_config.el_angles
    distances_m = _distances_m(captured_heat[0][3], subsweep_config)
    el_idx_zero = int(np.argmin(np.abs(el_angles)))

    # Ground truth: robust_capon's top-NUM_PEAKS peaks. Used as gray X markers in
    # every heatmap and as the reference index for the comparison figures.
    robust_capon_entry = next(
        (entry for entry in captured_heat if entry[0] == "robust_capon"), None
    )
    if robust_capon_entry is None:
        msg = "robust_capon result is required as ground truth but was not captured."
        raise RuntimeError(msg)
    rc_3d = robust_capon_entry[3]
    rc_daz = rc_3d[:, :, el_idx_zero]
    ground_truth_peaks = _find_top_peaks(rc_daz, distances_m, az_angles, NUM_PEAKS)
    if not ground_truth_peaks:
        msg = "No finite peaks found in the robust_capon heatmap for the selected frame."
        raise RuntimeError(msg)
    ref_d_idx, ref_az_idx = ground_truth_peaks[0]
    ref_el_idx = int(np.argmax(rc_3d[ref_d_idx, ref_az_idx, :]))

    # Per-beamformer figures - every beamformer's plot uses the SAME 3 peak
    # locations from robust_capon, so the colored markers and 1D cuts are
    # taken at identical (d, az) coordinates across the four plots.
    for name, _is_coherent, _result, heatmap_3d in captured_heat:
        daz = heatmap_3d[:, :, el_idx_zero]
        _plot_daz_with_marginals(
            name=name,
            heatmap_2d=daz,
            distances_m=distances_m,
            az_angles=az_angles,
            peaks=ground_truth_peaks,
            output_path=output_dir / f"heatmap_{name}.png",
            color_scale=args.color_scale,
        )

        _plot_el_spectrum(
            name=name,
            heatmap_3d=heatmap_3d,
            el_angles=el_angles,
            peaks=ground_truth_peaks,
            output_path=output_dir / f"el_spectrum_{name}.png",
            color_scale=args.color_scale,
        )

    # Comparison figures (overlay all beamformers at the robust_capon ground-truth indices).
    # Coherent's heatmap is an amplitude |s^H x|, while the others are powers |s^H x|^2 -
    # square it so all four are on the same power scale for the overlay.
    all_3d = [
        (name, heatmap_3d**2 if is_coherent else heatmap_3d)
        for name, is_coherent, _, heatmap_3d in captured_heat
    ]
    _plot_comparison_az(
        results=all_3d,
        az_angles=az_angles,
        peak_d_idx=ref_d_idx,
        peak_el_idx=ref_el_idx,
        output_path=output_dir / "comparison_az.png",
        color_scale=args.color_scale,
    )
    _plot_comparison_el(
        results=all_3d,
        el_angles=el_angles,
        peak_d_idx=ref_d_idx,
        peak_az_idx=ref_az_idx,
        output_path=output_dir / "comparison_el.png",
        color_scale=args.color_scale,
    )

    print(f"[plot_beamformers] wrote figures to: {output_dir}")


if __name__ == "__main__":
    main()
