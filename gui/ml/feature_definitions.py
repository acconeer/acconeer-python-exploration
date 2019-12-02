import os
import sys

import numpy as np


try:
    sys.path.append(os.path.join(os.path.dirname(__file__), "../../"))
    from examples.processing import presence_detection_sparse
except Exception as e:
    print("Could not import presence detector:\n", e)
    DETECTORS_SUPPORTED = False
else:
    DETECTORS_SUPPORTED = True


def get_features():
    features = {
        "sweep": {
            "name": "Range segment",
            "class": FeatureSweep,

            "model": "2D",
            "data_type": "envelope",
        },
        "peak": {
            "name": "Peak",
            "class": FeaturePeak,
            "model": "2D",
            "data_type": "envelope",
        },
        "averages_1d": {
            "name": "Averages 1D",
            "class": FeatureAverages1D,
            "model": "1D",
            "data_type": "envelope",
        },
        "averages_2d": {
            "name": "Averages 2D",
            "class": FeatureAverages2D,
            "model": "2D",
            "data_type": "envelope",
        },
        "amplitude_ratios_1d": {
            "name": "Amplitude Ratios 1D",
            "class": FeatureAmplitudeRatios1D,
            "model": "1D",
            "data_type": "envelope",
        },
        "sparse_fft": {
            "name": "Sparse FFT",
            "class": FeatureSparseFFT,
            "model": "2D",
            "data_type": "sparse",
        },
    }

    if DETECTORS_SUPPORTED:
        features["sparse_presence"] = {
            "name": "Presence Sparse",
            "class": FeatureSparsePresence,
            "model": "2D",
            "data_type": "sparse",
        }

    return features


def m2idx(value, array):
    idx = max(0, int(124/60 * (value * 1000 - array[0])))
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

    def extract_feature(self, win_data, sensor_idx, options=None, dist_vec=None):
        try:
            arr = win_data["env_data"][sensor_idx, :, :]
        except Exception:
            print("env_data not available!")
            return None

        # dist_vec is in mm
        data_len, win_len = arr.shape
        start = m2idx(options["Start"], dist_vec)
        stop = min(m2idx(options["Stop"], dist_vec), data_len)

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

    def extract_feature(self, win_data, sensor_idx, options=None, dist_vec=None):
        try:
            arr = win_data["env_data"][sensor_idx, :, :]
        except Exception:
            print("env_data not available!")
            return None

        # dist_vec is in mm
        data_len, win_len = arr.shape
        start = m2idx(options["Start"], dist_vec)
        stop = min(m2idx(options["Stop"], dist_vec), data_len)

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

    def extract_feature(self, win_data, sensor_idx, options=None, dist_vec=None):
        try:
            arr = win_data["env_data"][sensor_idx, :, :]
        except Exception:
            print("env_data not available!")
            return None

        # dist_vec is in mm
        data_len, win_len = arr.shape
        start = m2idx(options["Start"], dist_vec)
        stop = min(m2idx(options["Stop"], dist_vec), data_len)

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

    def extract_feature(self, win_data, sensor_idx, options=None, dist_vec=None):
        try:
            if sensor_idx == 1:
                arr = win_data["env_data"]
            else:
                return None
        except Exception:
            print("env_data not available!")
            return None

        # dist_vec is in mm
        nr_sensors, data_len, win_len = arr.shape
        start = m2idx(options["Start"], dist_vec)
        stop = min(m2idx(options["Stop"], dist_vec), data_len)

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
        }
        # text, value, limits
        self.options = [
            ("Start", 0.2, [0.06, 7], float),
            ("Stop", 0.4, [0.06, 7], float),
            ("Down sample", 8, [1, 124], int),
        ]

    def extract_feature(self, win_data, sensor_idx, options=None, dist_vec=None):
        try:
            arr = win_data["env_data"][sensor_idx, :, :]
        except Exception:
            print("env_data not available!")
            return None

        # dist_vec is in mm
        data_len, win_len = arr.shape
        start = m2idx(options["Start"], dist_vec)
        stop = min(m2idx(options["Stop"], dist_vec), data_len)
        downsampling = int(max(1, options["Down sample"]))

        if start >= stop:
            return None

        data = {
            "segment": arr[start:stop:downsampling, :],
        }

        return data

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
        }
        # text, value, limits
        self.options = [
            ("Start", 0.2, [0.06, 7], float),
            ("Stop", 0.4, [0.06, 7], float),
            ("High pass", 1, [0, 1], float),
        ]

    def extract_feature(self, win_data, sensor_idx, options=None, dist_vec=None):
        try:
            arr = win_data["sparse_data"][sensor_idx, :, :, :]
        except Exception:
            print("sparse_data not available!")
            return None

        point_repeats, data_len, win_len = arr.shape
        data_start = dist_vec[0]
        data_stop = dist_vec[-1]

        # dist_vec is in mm
        start = max(data_start, options["Start"] * 1000)
        stop = min(data_stop, options["Stop"] * 1000)
        high_pass = options["High pass"]

        if start >= data_stop:
            return None

        start_idx = np.argmin((dist_vec - start)**2)
        stop_idx = np.argmin((dist_vec - stop)**2)

        stop_idx = max(start_idx + 1, stop_idx)

        arr = arr[:, start_idx:stop_idx, :]

        hanning = np.hanning(point_repeats)[:, np.newaxis, np.newaxis]
        doppler = abs(np.fft.rfft(hanning * (arr - np.mean(arr, axis=0, keepdims=True)), axis=0))
        fft_psd = np.mean(doppler, axis=1) / 10000

        freq_bins = fft_psd.shape[0]
        freq_cutoff = int(high_pass * freq_bins)

        data = {
            "fft": fft_psd[0:freq_cutoff, :],
        }

        return data

    def get_options(self):
        return self.data, self.options

    def get_size(self, options=None):
        if options is None or "subsweeps" not in options:
            return 1
        try:
            size = int(np.ceil(options["subsweeps"] * options["High pass"] / 2))
        except Exception as e:
            print("Failed to calculate feature hight!\n ", e)
            return 1
        return int(size)


class FeatureSparsePresence:
    def __init__(self):
        # output data
        self.data = {
            "presence": "Presence",
        }
        # text, value, limits
        self.options = [
            ("Start", 0.2, [0.06, 7], float),
            ("Stop", 0.4, [0.06, 7], float),
        ]

        self.detector_processor = None
        self.history = None

    def extract_feature(self, win_data, sensor_idx, options=None, dist_vec=None):
        try:
            num_sensors = win_data["sparse_data"].shape[0]
            if self.detector_processor is None:
                self.detector_processor = [None] * num_sensors
                self.history = None
            arr = win_data["sparse_data"][sensor_idx, :, :, :]
            sensor_config = options["sensor_config"]
            session_info = options["session_info"]
        except Exception as e:
            print("sparse_data not available!\n", e)
            return None

        point_repeats, data_len, win_len = arr.shape
        data_start = dist_vec[0]
        data_stop = dist_vec[-1]

        # dist_vec is in mm
        start = max(data_start, options["Start"] * 1000)
        stop = min(data_stop, options["Stop"] * 1000)

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
            detector_handle = presence_detection_sparse.PresenceDetectionSparseProcessor
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

        data = {
            "presence": self.history[sensor_idx, start_idx:stop_idx, :],
        }

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
