# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from copy import copy
from enum import Enum
from typing import Optional

import numpy as np

import acconeer.exptool as et

from .calibration import DistanceDetectorCalibration


PEAK_MERGE_LIMIT_M = 0.005


def get_sensor_config():
    config = et.a111.EnvelopeServiceConfig()
    config.range_interval = [0.2, 0.6]
    config.update_rate = 40
    config.gain = 0.5
    config.running_average_factor = 0  # Use averaging in detector instead of in API

    return config


class Processor:
    def __init__(self, sensor_config, processing_config, session_info, calibration=None):
        self.session_info = session_info

        self.f = sensor_config.update_rate

        self.num_depths = self.session_info["data_length"]

        self.current_mean_sweep = np.zeros(self.num_depths)
        self.last_mean_sweep = np.full(self.num_depths, np.nan)
        self.sweeps_since_mean = 0

        self.sc_sum_bg_sweeps = np.zeros(self.num_depths)
        self.sc_sum_squared_bg_sweeps = np.zeros(self.num_depths)
        self.sc_used_threshold = np.full(self.num_depths, np.nan)
        self.calibration: Optional[DistanceDetectorCalibration] = None

        self.sc_bg_calculated = False

        self.history_length_s = processing_config.history_length_s
        self.main_peak_hist_sweep_idx = []
        self.main_peak_hist_dist = []
        self.minor_peaks_hist_sweep_idx = []
        self.minor_peaks_hist_dist = []
        self.above_thres_hist_sweep_idx = []
        self.above_thres_hist_dist = []

        self.r = et.a111.get_range_depths(sensor_config, session_info)
        self.dr = self.r[1] - self.r[0]
        self.sweep_index = 0

        self.update_processing_config(processing_config)

        self.update_calibration(calibration)

    def update_processing_config(self, processing_config):
        self.nbr_average = processing_config.nbr_average
        self.threshold_type = processing_config.threshold_type
        self.peak_sorting_method = processing_config.peak_sorting_type

        self.fixed_threshold_level = processing_config.fixed_threshold

        self.sc_sensitivity = processing_config.sc_sensitivity
        self.sc_bg_nbr_sweeps = processing_config.sc_nbr_sweep_for_bg

        self.idx_cfar_pts = np.round(
            (
                processing_config.cfar_guard_m / 2.0 / self.dr
                + np.arange(processing_config.cfar_window_m / self.dr)
            )
        )

        self.cfar_one_sided = processing_config.cfar_one_sided
        self.cfar_sensitivity = processing_config.cfar_sensitivity

        self.update_sc_threshold()
        self.max_nbr_peaks_to_plot = processing_config.max_nbr_peaks_to_plot
        self.history_length_s = processing_config.history_length_s

    def update_calibration(self, new_calibration: DistanceDetectorCalibration):
        self.calibration = new_calibration
        self.update_sc_threshold()

    @property
    def sc_used_mean(self):
        if self.calibration is None:
            return np.full(self.num_depths, np.nan)
        else:
            return self.calibration.stationary_clutter_mean

    @property
    def sc_used_std(self):
        if self.calibration is None:
            return np.full(self.num_depths, np.nan)
        else:
            return self.calibration.stationary_clutter_std

    def update_sc_threshold(self):
        self.sc_used_threshold = (
            self.sc_used_mean + (1.0 / (self.sc_sensitivity + 1e-10) - 1.0) * self.sc_used_std
        )

    def get_sc_threshold(self, sweep) -> Optional[DistanceDetectorCalibration]:
        # Collect first sweeps to construct a stationary clutter threshold
        # Accumulate sweeps instead of saving each for lower memory footprint
        calibration = None

        if self.sweep_index < self.sc_bg_nbr_sweeps:
            self.sc_sum_bg_sweeps += sweep
            self.sc_sum_squared_bg_sweeps += np.square(sweep)

        if self.sweep_index >= self.sc_bg_nbr_sweeps - 1 and not self.sc_bg_calculated:
            sc_bg_sweep_mean = self.sc_sum_bg_sweeps / self.sc_bg_nbr_sweeps
            mean_square = self.sc_sum_squared_bg_sweeps / self.sc_bg_nbr_sweeps
            square_mean = np.square(sc_bg_sweep_mean)
            sc_bg_sweep_std = np.sqrt(
                (mean_square - square_mean) * self.sc_bg_nbr_sweeps / (self.sc_bg_nbr_sweeps - 1)
            )
            calibration = DistanceDetectorCalibration(
                sc_bg_sweep_mean,
                sc_bg_sweep_std,
            )

            self.sc_bg_calculated = True

        return calibration

    def calculate_cfar_threshold(self, sweep, idx_cfar_pts, alpha, one_side):

        threshold = np.full(sweep.shape, np.nan)

        start_idx = np.max(idx_cfar_pts)
        if one_side:
            rel_indexes = -idx_cfar_pts
            end_idx = sweep.size
        else:
            rel_indexes = np.concatenate((-idx_cfar_pts, +idx_cfar_pts), axis=0)
            end_idx = sweep.size - start_idx

        for idx in np.arange(start_idx, end_idx):
            threshold[int(idx)] = (
                1.0 / (alpha + 1e-10) * np.mean(sweep[(idx + rel_indexes).astype(int)])
            )

        return threshold

    def find_first_point_above_threshold(self, sweep, threshold):

        if threshold is None or np.all(np.isnan(threshold)):
            return None

        points_above = sweep > threshold

        if not np.any(points_above):
            return None

        return np.argmax(points_above)

    def find_peaks(self, sweep, threshold):
        #  Not written for optimal speed.

        if threshold is None or np.all(np.isnan(threshold)):
            return []

        found_peaks = []

        # Note: at least 3 samples above threshold are required to form a peak

        d = 1
        N = len(sweep)
        while d < (N - 1):
            # Skip to when threshold starts, applicable only for CFAR
            if np.isnan(threshold[d - 1]):
                d += 1
                continue

            # Break when threshold ends, applicable only for CFAR
            if np.isnan(threshold[d + 1]):
                break

            # At this point, threshold is defined (not Nan)

            # If the current point is not over threshold, the next will not be a peak
            if sweep[d] <= threshold[d]:
                d += 2
                continue

            # Continue if previous point is not over threshold
            if sweep[d - 1] <= threshold[d - 1]:
                d += 1
                continue

            # Continue if this point isn't larger than the previous
            if sweep[d - 1] >= sweep[d]:
                d += 1
                continue

            # A peak is either a single point or a plateau consisting of several equal points,
            # all over their threshold. The closest neighboring points on each side of the
            # point/plateau must have a lower value and be over their threshold.
            # Now, decide if the following point(s) are a peak:

            d_upper = d + 1
            while True:
                if (d_upper) >= (N - 1):  # If out of range or on last point
                    break

                if np.isnan(threshold[d_upper]):
                    break

                if sweep[d_upper] <= threshold[d_upper]:
                    break

                if sweep[d_upper] > sweep[d]:
                    break
                elif sweep[d_upper] < sweep[d]:
                    delta = d_upper - d
                    found_peaks.append(d + int(np.ceil((delta - 1) / 2.0)))
                    break
                else:  # equal
                    d_upper += 1

            d = d_upper

        return found_peaks

    def merge_peaks(self, peak_indexes, merge_max_range):
        merged_peaks = copy(peak_indexes)

        while True:
            num_neighbors = np.zeros(len(merged_peaks))  # number of neighbors
            for i, p in enumerate(merged_peaks):
                num_neighbors[i] = np.sum(np.abs(np.array(merged_peaks) - p) < merge_max_range)

            # First peak with max number of neighbors
            i_peak = np.argmax(num_neighbors)  # returns arg of first max

            if num_neighbors[i_peak] <= 1:
                break

            peak = merged_peaks[i_peak]

            remove_mask = np.abs(np.array(merged_peaks) - peak) < merge_max_range
            peaks_to_remove = np.array(merged_peaks)[remove_mask]

            for p in peaks_to_remove:
                merged_peaks.remove(p)

            # Add back mean peak
            merged_peaks.append(int(round(np.mean(peaks_to_remove))))

            merged_peaks.sort()

        return merged_peaks

    def sort_peaks(self, peak_indexes, sweep):
        amp = np.array([sweep[int(i)] for i in peak_indexes])
        r = np.array([self.r[int(i)] for i in peak_indexes])

        PeakSorting = ProcessingConfiguration.PeakSorting
        if self.peak_sorting_method == PeakSorting.CLOSEST:
            quantity_to_sort = r
        elif self.peak_sorting_method == PeakSorting.STRONGEST:
            quantity_to_sort = -amp
        elif self.peak_sorting_method == PeakSorting.STRONGEST_REFLECTOR:
            quantity_to_sort = -amp * r**2
        elif self.peak_sorting_method == PeakSorting.STRONGEST_FLAT_REFLECTOR:
            quantity_to_sort = -amp * r
        else:
            raise Exception("Unknown peak sorting method")

        return [peak_indexes[i] for i in quantity_to_sort.argsort()]

    def process(self, data, data_info):
        sweep = data

        # Accumulate sweeps for stationary clutter threshold and check if user has
        # loaded one from disk
        new_calibration = self.get_sc_threshold(sweep)

        # Average envelope sweeps, written to handle varying nbr_average
        weight = 1.0 / (1.0 + self.sweeps_since_mean)
        self.current_mean_sweep = weight * sweep + (1.0 - weight) * self.current_mean_sweep
        self.sweeps_since_mean += 1

        # Determining threshold
        if self.threshold_type is ProcessingConfiguration.ThresholdType.FIXED:
            threshold = self.fixed_threshold_level * np.ones(sweep.size)
        elif self.threshold_type is ProcessingConfiguration.ThresholdType.RECORDED:
            threshold = self.sc_used_threshold
        elif self.threshold_type is ProcessingConfiguration.ThresholdType.CFAR:
            threshold = self.calculate_cfar_threshold(
                self.current_mean_sweep,
                self.idx_cfar_pts,
                self.cfar_sensitivity,
                self.cfar_one_sided,
            )
        else:
            print("Unknown thresholding method")

        found_peaks = None

        # If a new averaged sweep is ready for processing
        if self.sweeps_since_mean >= self.nbr_average:
            self.sweeps_since_mean = 0
            self.last_mean_sweep = self.current_mean_sweep.copy()
            self.current_mean_sweep *= 0

            # Find the first delay over threshold. Used in tank-level when monitoring changes
            # in the direct leakage.
            first_point_above_threshold = self.find_first_point_above_threshold(
                self.last_mean_sweep, threshold
            )

            # First peak-finding, then peak-merging, finallay peak sorting.
            found_peaks = self.find_peaks(self.last_mean_sweep, threshold)
            if len(found_peaks) > 1:
                found_peaks = self.merge_peaks(found_peaks, np.round(PEAK_MERGE_LIMIT_M / self.dr))
                found_peaks = self.sort_peaks(found_peaks, self.last_mean_sweep)

            # Adding main peak to history
            if len(found_peaks) > 0:
                self.main_peak_hist_sweep_idx.append(self.sweep_index)
                self.main_peak_hist_dist.append(self.r[found_peaks[0]])

            # Adding minor peaks to history
            for i in range(1, min(len(found_peaks), self.max_nbr_peaks_to_plot)):
                self.minor_peaks_hist_sweep_idx.append(self.sweep_index)
                self.minor_peaks_hist_dist.append(self.r[found_peaks[i]])

            # Adding first distance above threshold to history
            if first_point_above_threshold is not None:
                self.above_thres_hist_sweep_idx.append(self.sweep_index)
                self.above_thres_hist_dist.append(self.r[first_point_above_threshold])

            # Removing old main peaks from history
            while (
                len(self.main_peak_hist_sweep_idx) > 0
                and self.sweep_index - self.main_peak_hist_sweep_idx[0]
                > self.history_length_s * self.f
            ):
                self.main_peak_hist_sweep_idx.pop(0)
                self.main_peak_hist_dist.pop(0)

            # Removing old minor peaks from history
            while (
                len(self.minor_peaks_hist_sweep_idx) > 0
                and self.sweep_index - self.minor_peaks_hist_sweep_idx[0]
                > self.history_length_s * self.f
            ):
                self.minor_peaks_hist_sweep_idx.pop(0)
                self.minor_peaks_hist_dist.pop(0)

            # Removing old first distance above threshold from history
            while (
                len(self.above_thres_hist_sweep_idx) > 0
                and self.sweep_index - self.above_thres_hist_sweep_idx[0]
                > self.history_length_s * self.f
            ):
                self.above_thres_hist_sweep_idx.pop(0)
                self.above_thres_hist_dist.pop(0)

        out_data = {
            "sweep": sweep,
            "last_mean_sweep": self.last_mean_sweep,
            "threshold": threshold,
            "main_peak_hist_sweep_s": (
                (np.array(self.main_peak_hist_sweep_idx) - self.sweep_index) / self.f
            ),
            "main_peak_hist_dist": np.array(self.main_peak_hist_dist),
            "minor_peaks_hist_sweep_s": (
                (np.array(self.minor_peaks_hist_sweep_idx) - self.sweep_index) / self.f
            ),
            "minor_peaks_hist_dist": np.array(self.minor_peaks_hist_dist),
            "above_thres_hist_sweep_s": (
                (np.array(self.above_thres_hist_sweep_idx) - self.sweep_index) / self.f
            ),
            "above_thres_hist_dist": np.array(self.above_thres_hist_dist),
            "sweep_index": self.sweep_index,
            "found_peaks": found_peaks,
        }

        if new_calibration:
            out_data["new_calibration"] = new_calibration

        self.sweep_index += 1

        return out_data


class ProcessingConfiguration(et.configbase.ProcessingConfig):
    class ThresholdType(Enum):
        FIXED = "Fixed"
        RECORDED = "Recorded"
        CFAR = "CFAR"

    class PeakSorting(Enum):
        STRONGEST = "Strongest signal"
        CLOSEST = "Closest signal"
        STRONGEST_REFLECTOR = "Strongest reflector"
        STRONGEST_FLAT_REFLECTOR = "Strongest flat reflector"

    VERSION = 2

    nbr_average = et.configbase.FloatParameter(
        label="Sweep averaging",
        default_value=5,
        limits=(1, 100),
        logscale=True,
        decimals=0,
        updateable=True,
        order=0,
        visible=True,
        help=(
            "The number of envelope sweeps to be average into one then used for"
            " distance detection."
        ),
    )

    threshold_type = et.configbase.EnumParameter(
        label="Threshold type",
        default_value=ThresholdType.FIXED,
        enum=ThresholdType,
        updateable=True,
        order=5,
        help="Setting the type of threshold",
    )

    fixed_threshold = et.configbase.FloatParameter(
        label="Fixed threshold level",
        default_value=800,
        limits=(1, 20000),
        decimals=0,
        updateable=True,
        order=10,
        visible=lambda conf: conf.threshold_type == conf.ThresholdType.FIXED,
        help=(
            "Sets the value of fixed threshold. The threshold has this constant value over"
            " the full sweep."
        ),
    )

    sc_nbr_sweep_for_bg = et.configbase.FloatParameter(
        label="Number of sweeps for background estimation",
        default_value=20,
        limits=(2, 200),
        decimals=0,
        visible=lambda conf: conf.threshold_type == conf.ThresholdType.RECORDED,
        updateable=True,
        order=20,
        help=(
            "The number of (non-averaged) sweeps collected for calculating the Stationary"
            " Clutter threshold."
        ),
    )

    sc_sensitivity = et.configbase.FloatParameter(
        label="Stationary clutter sensitivity",
        default_value=0.3,
        limits=(0.01, 1),
        logscale=True,
        visible=lambda conf: conf.threshold_type == conf.ThresholdType.RECORDED,
        decimals=4,
        updateable=True,
        order=24,
        help=(
            "Value between 0 and 1 that sets the threshold. A low sensitivity will set a "
            "high threshold, resulting in only few false alarms but might result in "
            "missed detections."
        ),
    )

    cfar_sensitivity = et.configbase.FloatParameter(
        label="CFAR sensitivity",
        default_value=0.5,
        limits=(0.01, 1),
        logscale=True,
        visible=lambda conf: conf.threshold_type == conf.ThresholdType.CFAR,
        decimals=4,
        updateable=True,
        order=40,
        help=(
            "Value between 0 and 1 that sets the threshold. A low sensitivity will set a "
            "high threshold, resulting in only few false alarms but might result in "
            "missed detections."
        ),
    )

    cfar_guard_m = et.configbase.FloatParameter(
        label="CFAR guard",
        default_value=0.12,
        limits=(0.01, 0.2),
        unit="m",
        decimals=3,
        visible=lambda conf: conf.threshold_type == conf.ThresholdType.CFAR,
        updateable=True,
        order=41,
        help=(
            "Range around the distance of interest that is omitted when calculating "
            "CFAR threshold. Can be low, ~40 mm, for Profile 1, and should be "
            "increased for higher Profiles."
        ),
    )

    cfar_window_m = et.configbase.FloatParameter(
        label="CFAR window",
        default_value=0.03,
        limits=(0.001, 0.2),
        unit="m",
        decimals=3,
        visible=lambda conf: conf.threshold_type == conf.ThresholdType.CFAR,
        updateable=True,
        order=42,
        help="Range next to the CFAR guard from which the threshold level will be calculated.",
    )

    cfar_one_sided = et.configbase.BoolParameter(
        label="Use only lower distance to set threshold",
        default_value=False,
        visible=lambda conf: conf.threshold_type == conf.ThresholdType.CFAR,
        updateable=True,
        order=43,
        help=(
            "Instead of determining the CFAR threshold from sweep amplitudes from "
            "distances both closer and a farther, use only closer. Helpful e.g. for "
            "fluid level in small tanks, where many multipath signal can apprear "
            "just after the main peak."
        ),
    )

    peak_sorting_type = et.configbase.EnumParameter(
        label="Peak sorting",
        default_value=PeakSorting.STRONGEST,
        enum=PeakSorting,
        updateable=True,
        order=100,
        help="Setting the type of peak sorting method.",
    )

    history_length_s = et.configbase.FloatParameter(
        default_value=10,
        limits=(3, 1000),
        updateable=True,
        logscale=True,
        unit="s",
        label="History length",
        order=198,
        help="Length of time history for plotting.",
    )

    max_nbr_peaks_to_plot = et.configbase.IntParameter(
        default_value=1,
        limits=(1, 15),
        updateable=True,
        unit="peaks",
        label="Peaks per sweep in plot",
        order=200,
        help="The maximum number of peaks per averaged sweep to be plotted in the lower figure.",
    )

    show_first_above_threshold = et.configbase.BoolParameter(
        label="Show first distance above threshold",
        default_value=False,
        updateable=True,
        order=201,
        help=(
            "When detect in the presence of object very close to the sensor, the "
            "strong direct leakage might cause that no well shaped peaks are detected, "
            "even though the envelope signal is above the threshold. Therefore the "
            "first distace where the signal is above the threshold can be used as an "
            "alternative to peak detection."
        ),
    )

    def check_sensor_config(self, sensor_config):
        alerts = {
            "processing": [],
            "sensor": [],
        }
        if sensor_config.update_rate is None:
            alerts["sensor"].append(et.configbase.Error("update_rate", "Must be set"))

        if not sensor_config.noise_level_normalization:
            if self.threshold_type == self.ThresholdType.FIXED:
                alerts["sensor"].append(
                    et.configbase.Warning(
                        "noise_level_normalization",
                        (
                            "Enabling noise level normalization is\n"
                            "recommended with Fixed threshold"
                        ),
                    )
                )

        return alerts
