import os
import sys

import numpy as np

from acconeer.exptool.modes import Mode


try:
    sys.path.append(os.path.join(os.path.dirname(__file__), "../../"))
    from examples.processing import distance_detector, presence_detection_sparse
except Exception as e:
    print("Could not import detectors\n", e)
    DETECTORS_SUPPORTED = False
else:
    DETECTORS_SUPPORTED = True


def get_features():
    features = {
        "sweep": {
            "name": "Range segment",
            "class": FeatureSweep,
            "model": "2D",
            "data_type": Mode.ENVELOPE,
        },
        "peak": {
            "name": "Peak",
            "class": FeaturePeak,
            "model": "2D",
            "data_type": Mode.ENVELOPE,
        },
        "averages_1d": {
            "name": "Averages 1D",
            "class": FeatureAverages1D,
            "model": "1D",
            "data_type": Mode.ENVELOPE,
        },
        "averages_2d": {
            "name": "Averages 2D",
            "class": FeatureAverages2D,
            "model": "2D",
            "data_type": Mode.ENVELOPE,
        },
        "amplitude_ratios_1d": {
            "name": "Amplitude Ratios 1D",
            "class": FeatureAmplitudeRatios1D,
            "model": "1D",
            "data_type": Mode.ENVELOPE,
        },
        "sparse_fft": {
            "name": "Sparse FFT",
            "class": FeatureSparseFFT,
            "model": "2D",
            "data_type": Mode.SPARSE,
        },
    }

    if DETECTORS_SUPPORTED:
        features["sparse_presence"] = {
            "name": "Presence Sparse",
            "class": FeatureSparsePresence,
            "model": "2D",
            "data_type": Mode.SPARSE,
        }
        features["distance_envelope"] = {
            "name": "Distance Envelope",
            "class": FeatureDistanceEnvelope,
            "model": "1D",
            "data_type": Mode.ENVELOPE,
        }

    return features


def distance2idx(value, dist_vec):
    idx = np.argmin((dist_vec - value)**2)
    return int(idx)


class FeaturePeak:
    def __init__(self):
        # output data
        self.data = {
            "peak": "Distance",
            "amplitude": "Amplitude",
        }
        # text, value, limits, type
        self.options = [
            ("Start", 0.2, [0.06, 7], float),
            ("Stop", 0.4, [0.06, 7], float),
            ("LP filter", 0.1, [0, 1], float),
        ]

    def extract_feature(self, win_data, win_params):
        try:
            sensor_idx = win_params["sensor_idx"]
            dist_vec = win_params["dist_vec"]
            options = win_params["options"]
            arr = win_data["env_data"][sensor_idx, :, :]
        except Exception:
            print("env_data not available!")
            return None

        # dist_vec is in mm
        data_len, win_len = arr.shape
        start = distance2idx(options["Start"] * 1000, dist_vec)
        stop = distance2idx(options["Stop"] * 1000, dist_vec) + 1

        if start >= stop:
            return None

        peak = np.zeros((win_len, 4))
        for i in range(win_len):
            idx = np.argmax(arr[start:stop, i]) + start
            peak[i, 0] = dist_vec[int(idx)]
            peak[i, 1] = arr[int(idx), i]

        data = {
            "peak": peak[:, 0],
            "amplitude": peak[:, 1],
        }

        return data

    def get_options(self):
        return self.data, self.options

    def get_size(self, options=None):
        return 1


class FeatureAverages1D():
    def __init__(self):
        # output data
        self.data = {
            "avg_dist": "Avg. dist.",
            "avg_std": "Avg. std.",
            "avg_ampl": "Avg. ampl.",
            "avg_total": "Avg. total",
        }
        # text, value, limits
        self.options = [
            ("Start", 0.2, [0.06, 7], float),
            ("Stop", 0.4, [0.06, 7], float),
        ]

    def extract_feature(self, win_data, win_params):
        try:
            sensor_idx = win_params["sensor_idx"]
            dist_vec = win_params["dist_vec"]
            options = win_params["options"]
            arr = win_data["env_data"][sensor_idx, :, :]
        except Exception as e:
            print("env_data not available!\n", e)
            return None

        # dist_vec is in mm
        data_len, win_len = arr.shape
        start = distance2idx(options["Start"] * 1000, dist_vec)
        stop = distance2idx(options["Stop"] * 1000, dist_vec) + 1

        if start >= stop:
            return None

        peak = np.zeros((win_len, 3))
        for i in range(win_len):
            idx = np.argmax(arr[start:stop, i]) + start
            peak[i, 0] = dist_vec[int(idx)]
            peak[i, 1] = arr[int(idx), i]
            peak[i, 2] = np.sum(arr[start:stop, i])

        data = {
            "avg_dist": np.mean(peak[:, 0]),
            "avg_std": np.std(peak[:, 0]),
            "avg_ampl": np.mean(peak[:, 1]),
            "avg_total": np.mean(peak[:, 2]),
        }

        return data

    def get_options(self):
        return self.data, self.options

    def get_size(self, options=None):
        return 1


class FeatureAverages2D():
    def __init__(self):
        # output data
        self.data = {
            "avg_dist": "Avg. dist.",
            "avg_std": "Avg. std.",
            "avg_ampl": "Avg. ampl.",
            "avg_total": "Avg. signal",
        }
        # text, value, limits
        self.options = [
            ("Start", 0.2, [0.06, 7], float),
            ("Stop", 0.4, [0.06, 7], float),
        ]

    def extract_feature(self, win_data, win_params):
        try:
            sensor_idx = win_params["sensor_idx"]
            dist_vec = win_params["dist_vec"]
            options = win_params["options"]
            arr = win_data["env_data"][sensor_idx, :, :]
        except Exception as e:
            print("env_data not available!\n", e)
            return None

        # dist_vec is in mm
        data_len, win_len = arr.shape
        start = distance2idx(options["Start"] * 1000, dist_vec)
        stop = distance2idx(options["Stop"] * 1000, dist_vec) + 1

        if start >= stop:
            return None

        peak = np.zeros((win_len, 3))
        for i in range(win_len):
            idx = np.argmax(arr[start:stop, i]) + start
            peak[i, 0] = dist_vec[int(idx)]
            peak[i, 1] = arr[int(idx), i]
            peak[i, 2] = np.sum(arr[start:stop, i])

        data = {
            "avg_dist": np.full(win_len, np.mean(peak[:, 0])),
            "avg_std": np.full(win_len, np.std(peak[:, 0])),
            "avg_ampl": np.full(win_len, np.mean(peak[:, 1])),
            "avg_total": np.full(win_len, np.mean(peak[:, 2])),
        }

        return data

    def get_options(self):
        return self.data, self.options

    def get_size(self, options=None):
        return 1


class FeatureAmplitudeRatios1D():
    def __init__(self):
        # output data
        self.data = {
            "avg_ratio": "Avg. Amp. ratio",
        }
        # text, value, limits
        self.options = [
            ("Start", 0.2, [0.06, 7], float),
            ("Stop", 0.4, [0.06, 7], float),
        ]

    def extract_feature(self, win_data, win_params):
        try:
            sensor_idx = win_params["sensor_idx"]
            dist_vec = win_params["dist_vec"]
            options = win_params["options"]
            if sensor_idx == 1:
                arr = win_data["env_data"]
            else:
                return None
        except Exception as e:
            print("env_data not available!\n", e)
            return None

        # dist_vec is in mm
        nr_sensors, data_len, win_len = arr.shape
        start = distance2idx(options["Start"] * 1000, dist_vec)
        stop = distance2idx(options["Stop"] * 1000, dist_vec)

        if start >= stop:
            return None

        peak = np.zeros((2, win_len, 4))
        for s in range(2):
            for i in range(win_len):
                idx = np.argmax(arr[s, start:stop, i]) + start
                peak[s, i, 0] = dist_vec[int(idx)]
                peak[s, i, 1] = arr[s, int(idx), i]
                peak[s, i, 2] = np.sum(arr[s, start:stop, i])

        data = {
            "avg_ratio": np.mean(peak[0, :, 1]) / np.mean(peak[1, :, 1]),
        }

        return data

    def get_options(self):
        return self.data, self.options

    def get_size(self, options=None):
        return 1


class FeatureSweep:
    def __init__(self):
        # output data
        self.data = {
            "segment": "Segment",
            "integrated": "Integrated"
        }
        # text, value, limits
        self.options = [
            ("Start", 0.2, [0.06, 7], float),
            ("Stop", 0.4, [0.06, 7], float),
            ("Down sample", 8, [1, 124], int),
            ("Flip", False, None, bool),
            ("Stretch", False, None, bool),
            ("Calibrate", False, None, bool),
        ]

        self.idx = 0
        self.bg = None
        self.downsampling = None
        self.calib = 100           # Number of frames to use for calibration
        self.dead_time = 200       # Number of frames to wait after calibration

    def extract_feature(self, win_data, win_params):
        try:
            sensor_idx = win_params["sensor_idx"]
            dist_vec = win_params["dist_vec"]
            options = win_params["options"]
            arr = win_data["env_data"][sensor_idx, :, :]
            num_sensors = win_data["env_data"].shape[0]
        except Exception as e:
            print("env_data not available!\n", e)
            return None

        # dist_vec is in mm
        data_len, win_len = arr.shape
        start = distance2idx(options["Start"] * 1000, dist_vec)
        stop = distance2idx(options["Stop"] * 1000, dist_vec)
        downsampling = int(max(1, options["Down sample"]))

        if downsampling != self.downsampling:
            self.downsampling = downsampling
            self.down_arr = None
            self.idx = 0

        last_vec = self.average(win_data["env_data"][sensor_idx, :, 0], self.downsampling)

        if self.down_arr is None:
            self.down_arr = np.zeros((num_sensors, last_vec.shape[0], win_len))

        self.down_arr[sensor_idx, :, :] = np.roll(self.down_arr[sensor_idx, :, :], 1, axis=1)
        self.down_arr[sensor_idx, :, 0] = last_vec

        if start >= stop:
            return None

        if options.get("Calibrate", False):
            if self.idx < self.calib:
                if not self.idx:
                    self.bg = np.zeros((num_sensors, self.down_arr.shape[1]))
                self.bg[sensor_idx, :] = np.maximum(
                        self.bg[sensor_idx, :],
                        1.05 * self.down_arr[sensor_idx, :, 0]
                )

            if self.idx < self.calib + self.dead_time:
                if sensor_idx == 3:
                    self.idx += 1
                return None
            elif self.idx == self.calib + self.dead_time and sensor_idx == 0:
                bg = np.empty_like(self.down_arr)
                for s in range(len(win_params["sensor_config"].sensor)):
                    for i in range(win_len):
                        bg[s, :, i] = self.bg[s, :]
                self.bg = bg
                self.idx += 1

            full_arr = self.down_arr / self.bg
            full_arr[full_arr < 1] = 1
        else:
            full_arr = self.down_arr

        if options["Stretch"]:
            map_max = 1.2 * np.max(full_arr)
            new_arr = full_arr[sensor_idx, :, :]
            g = 1 / 2.2
            new_arr = 254/(map_max - 1 + 1.0e-9)**g * (new_arr - 1)**g
            new_arr[new_arr < 1] = 1
        else:
            new_arr = full_arr[sensor_idx, :, :]

        if options["Flip"]:
            data = {
                "segment": np.flip(new_arr, 0),
            }
        else:
            data = {
                "segment": new_arr,
            }

        data["integrated"] = np.mean(data["segment"], axis=1)

        return data

    def average(self, vec, n):
        if n > 1:
            end = n * int(len(vec) / n)
            return np.mean(vec[:end].reshape(-1, n), 1)
        else:
            return vec

    def get_options(self):
        return self.data, self.options

    def get_size(self, options=None):
        if options is None:
            return 1
        try:
            start = float(options["Start"])
            stop = float(options["Stop"])
            downsample = int(options["Down sample"])
            size = (stop - start) * 100 * 124 / downsample / 6 + 1
        except Exception as e:
            print("Failed to calculate feature hight!\n ", e)
            return 1
        return int(size)


class FeatureSparseFFT:
    def __init__(self):
        # output data
        self.data = {
            "fft": "FFT PSD",
            "fft_profile": "FFT Profile",
            "fft_yprofile": "FFT y-Profile",
        }
        # text, value, limits
        self.options = [
            ("Start", 0.2, [0.06, 7], float),
            ("Stop", 0.4, [0.06, 7], float),
            ("High pass", 1, [0, 1], float),
            ("Flip", True, None, bool),
            ("Stretch", False, None, bool)
        ]
        self.fft = None
        self.noise_floor = None

    def extract_feature(self, win_data, win_params):
        try:
            sensor_idx = win_params["sensor_idx"]
            dist_vec = win_params["dist_vec"]
            options = win_params["options"]
            arr = win_data["sparse_data"][sensor_idx, :, :, :]
        except Exception as e:
            print("sparse_data not available!\n", e)
            return None

        point_repeats, data_len, win_len = arr.shape
        num_sensors = win_data["sparse_data"].shape[0]
        data_start = dist_vec[0]
        data_stop = dist_vec[-1]

        # dist_vec is in mm
        start = max(data_start, options["Start"] * 1000)
        stop = min(data_stop, options["Stop"] * 1000)
        high_pass = options["High pass"]

        if start >= data_stop:
            return None

        start_idx = np.argmin((dist_vec - start)**2)
        stop_idx = np.argmin((dist_vec - stop)**2) + 1

        stop_idx = max(start_idx + 1, stop_idx)

        sweep = arr[:, start_idx:stop_idx, 0]

        hanning = np.hanning(point_repeats)[:, np.newaxis]
        doppler = np.fft.rfft(hanning * (sweep - np.mean(sweep, axis=0, keepdims=True)), axis=0)
        doppler = abs(doppler)
        fft_psd = np.mean(doppler, axis=1) / 10000

        freq_bins = fft_psd.shape[0]
        freq_cutoff = int(high_pass * freq_bins)
        freq_cutoff_flipped = int((1.0 - high_pass) * freq_bins)

        if self.fft is None:
            self.fft = np.zeros((num_sensors, freq_bins, win_len))
        if self.noise_floor is None:
            self.noise_floor = np.full(num_sensors, np.inf)

        threshold = 1.0
        m = np.mean(fft_psd) * threshold
        if m < self.noise_floor[sensor_idx] and m > 1E-8:
            self.noise_floor[sensor_idx] = m

        fft_psd /= self.noise_floor[sensor_idx]
        self.fft[sensor_idx, :, :] = np.roll(self.fft[sensor_idx, :, :], 1, axis=1)

        if options["Flip"]:
            self.fft[sensor_idx, :, 0] = np.flip(fft_psd, 0)
            data = {
                "fft": self.fft[sensor_idx, freq_cutoff_flipped:, :].copy(),
            }
        else:
            self.fft[sensor_idx, :, 0] = fft_psd
            data = {
                "fft": self.fft[sensor_idx, 0:freq_cutoff+1, :].copy(),
            }

        data["fft_profile"] = np.sum(data["fft"], axis=0)
        min_profile = np.min(data["fft_profile"])
        max_profile = np.max(data["fft_profile"])
        data["fft_profile"] = (data["fft_profile"] - min_profile) / max_profile * 256

        data["fft_yprofile"] = np.sum(data["fft"], axis=1) / 6000 * 256

        # Apply normalized gamma stretch and subtract mean.
        if options.get("Stretch", None):
            map_max = 1.2 * np.max(data["fft"])
            g = 1 / 2.2
            data["fft"] = 254/(map_max + 1.0e-9)**g * data["fft"]**g
            avgs = np.mean(data["fft"], axis=0)
            data["fft"] -= np.min(avgs)
            data["fft"][data["fft"] < 0] = 0

        return data

    def get_options(self):
        return self.data, self.options

    def get_size(self, options=None):
        if options is None or "sweeps_per_frame" not in options:
            return 1
        try:
            size = int(np.ceil(options["sweeps_per_frame"] * options["High pass"] / 2))
        except Exception as e:
            print("Failed to calculate feature hight!\n ", e)
            return 1
        return size + 1


class FeatureSparsePresence:
    def __init__(self):
        # output data
        self.data = {
            "presence": "Presence",
            "presence_avg": "Time Average"
        }
        # text, value, limits
        self.options = [
            ("Start", 0.2, [0.06, 7], float),
            ("Stop", 0.4, [0.06, 7], float),
            ("Calibrate Avg.", False, None, bool)
        ]

        self.detector_processor = None
        self.history = None
        self.idx = 0
        self.last_cal = False
        self.avg_presence = None
        self.calib = 100                # Number of frames to use for calibration
        self.dead_time = 200            # Number of frames to wait after calibration

    def extract_feature(self, win_data, win_params):
        try:
            num_sensors = win_data["sparse_data"].shape[0]
            if self.detector_processor is None:
                self.detector_processor = [None] * num_sensors
                self.history = None
            sensor_config = win_params["sensor_config"]
            session_info = win_params["session_info"]
            sensor_idx = win_params["sensor_idx"]
            dist_vec = win_params["dist_vec"]
            options = win_params["options"]
            arr = win_data["sparse_data"][sensor_idx, :, :, :]
        except Exception as e:
            print("sparse_data not available!\n", e)
            return None

        point_repeats, data_len, win_len = arr.shape
        data_start = dist_vec[0]
        data_stop = dist_vec[-1]

        # dist_vec is in mm
        start = max(data_start, options["Start"] * 1000)
        stop = min(data_stop, options["Stop"] * 1000) + 1

        if start >= data_stop:
            return None

        start_idx = np.argmin((dist_vec - start)**2)
        stop_idx = np.argmin((dist_vec - stop)**2) + 1

        stop_idx = max(start_idx + 1, stop_idx)

        if self.detector_processor[sensor_idx] is None:
            detector_config = presence_detection_sparse.get_processing_config()
            detector_config.detection_threshold = 0
            detector_config.inter_frame_fast_cutoff = 100
            detector_config.inter_frame_slow_cutoff = 0.9
            detector_config.inter_frame_deviation_time_const = 0.05
            detector_config.intra_frame_time_const = 0.03
            detector_config.intra_frame_weight = 0.8
            detector_config.output_time_const = 0.01
            detector_handle = presence_detection_sparse.Processor
            self.detector_processor[sensor_idx] = detector_handle(
                sensor_config,
                detector_config,
                session_info
            )
            self.detector_processor[sensor_idx].depth_filter_length = 1

        detector_output = self.detector_processor[sensor_idx].process(arr[:, :, 0])
        presence = detector_output["depthwise_presence"]

        if self.history is None:
            self.history = np.zeros((num_sensors, len(presence), win_len))

        self.history[sensor_idx, :, :] = np.roll(self.history[sensor_idx, :, :], 1, axis=1)
        self.history[sensor_idx, :, 0] = presence

        presence = self.history[sensor_idx, start_idx:stop_idx, :]
        avg_presence = np.mean(presence, axis=1)

        if self.avg_presence is None:
            self.avg_presence = np.zeros((num_sensors, len(avg_presence)))

        if options.get("Calibrate Avg.", False):
            if self.idx == 0:
                self.bg = np.zeros((num_sensors, len(avg_presence)))
            if self.idx < self.calib:
                self.bg[sensor_idx, :] = np.maximum(self.bg[sensor_idx, :], 1.2 * avg_presence)
                if sensor_idx == num_sensors - 1:
                    self.idx += 1

            avg_presence = avg_presence / self.bg[sensor_idx, :]
            avg_presence[avg_presence < 1] = 1

        self.avg_presence[sensor_idx, :] = avg_presence
        avg_presence = avg_presence / np.max(self.avg_presence) * 256

        data = {
            "presence": presence,
            "presence_avg": avg_presence,
        }

        if self.last_cal != options.get("Calibrate Avg.", False):
            self.idx = 0
            self.last_cal = options.get("Calibrate Avg.", False)

        if options.get("Calibrate Avg.", False):
            if self.idx < self.calib + self.dead_time:
                data = None
                if sensor_idx == num_sensors - 1:
                    self.idx += 1

        return data

    def get_options(self):
        return self.data, self.options

    def get_size(self, options=None):
        if options is None:
            return 1
        try:
            start = float(options["Start"])
            stop = float(options["Stop"])
            size = int(np.ceil((stop - start) / 0.06)) + 1
        except Exception as e:
            print("Failed to calculate feature hight!\n ", e)
            return 1
        return int(size)


class FeatureDistanceEnvelope:
    def __init__(self):
        # output data
        self.data = {
            "distance": "Distance",
        }
        # text, value, limits
        self.options = [
            ("Start", 0.2, [0.06, 7], float),
            ("Stop", 0.4, [0.06, 7], float),
            ("Sweep Avg.", 100, [1, 100], int),
            ("Threshold", 600, [1, 20000], int),
        ]

        self.detector_processor = None

    def extract_feature(self, win_data, win_params):
        try:
            num_sensors = win_data["env_data"].shape[0]
            if self.detector_processor is None:
                self.detector_processor = [None] * num_sensors
                self.history = None
            sensor_config = win_params["sensor_config"]
            session_info = win_params["session_info"]
            sensor_idx = win_params["sensor_idx"]
            dist_vec = win_params["dist_vec"]
            options = win_params["options"]
            arr = win_data["env_data"][sensor_idx, :, :]
        except Exception as e:
            print("envelope_data not available!\n", e)
            return None

        data_len, win_len = arr.shape
        data_start = dist_vec[0]
        data_stop = dist_vec[-1]

        # dist_vec is in mm
        start = max(data_start, options["Start"] * 1000)
        stop = min(data_stop, options["Stop"] * 1000) + 1

        if start >= data_stop:
            return None

        start_idx = np.argmin((dist_vec - start)**2)
        stop_idx = np.argmin((dist_vec - stop)**2) + 1

        stop_idx = max(start_idx + 1, stop_idx)

        if self.detector_processor[sensor_idx] is None:
            detector_config = distance_detector.get_processing_config()
            detector_config.nbr_average = options["Sweep Avg."]
            detector_config.fixed_threshold = options["Threshold"]
            detector_config.history_length_s = win_len

            dist_enums = distance_detector.ProcessingConfiguration
            detector_config.threshold_type = dist_enums.ThresholdType.FIXED
            detector_config.peak_sorting_type = dist_enums.PeakSorting.STRONGEST

            detector_handle = distance_detector.Processor
            self.detector_processor[sensor_idx] = detector_handle(
                sensor_config,
                detector_config,
                session_info
            )

        detector_output = self.detector_processor[sensor_idx].process(arr[:, 0])
        distance = detector_output["main_peak_hist_dist"]

        if not len(distance):
            return None

        data = {
            "distance": distance[-1],
        }

        return data

    def get_options(self):
        return self.data, self.options

    def get_size(self, options=None):
        return 1
