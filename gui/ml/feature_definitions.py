import numpy as np


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
        }
    }

    return features


def m2idx(value, array):
    idx = max(0, int(124/60 * (value * 1000 - array[0])))
    return int(idx)


class FeaturePeak:
    def __init__(self):
        # output data
        self.data = {
            "peak": "Peak",
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

        center = (options["Stop"] * 1000 + options["Start"] * 1000) / 2
        if center <= 0:
            center = 1

        data = {
            "avg_dist": np.mean(peak[:, 0]) / center,
            "avg_std": np.std(peak[:, 0]),
            "avg_ampl": np.mean(peak[:, 1]) / (2**16 / 2),
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
            size = (stop - start) * 100 * 124 / downsample / 6
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

        # dist_vec is in m
        start = max(data_start, options["Start"])
        stop = min(data_stop, options["Stop"])
        high_pass = options["High pass"]

        if start >= data_stop:
            return None

        start_idx = np.argmin((dist_vec - start)**2)
        stop_idx = np.argmin((dist_vec - stop)**2)

        hanning = np.hanning(point_repeats)[:, np.newaxis, np.newaxis]
        doppler = abs(np.fft.rfft(hanning * (arr - np.mean(arr, axis=0, keepdims=True)), axis=0))
        fft_psd = np.sum(doppler, axis=1)

        freq_bins = fft_psd.shape[1]
        freq_cutoff = freq_bins - int(high_pass * freq_bins)
        left_cut = int(freq_cutoff / 2)
        right_cut = freq_bins - int(freq_cutoff / 2)
        fft_psd[:, 0:left_cut] = 0
        fft_psd[:, right_cut:] = 0

        data = {
            "fft": fft_psd[start_idx:stop_idx, :],
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
            size = (stop - start) * 100 / 6
        except Exception as e:
            print("Failed to calculate feature hight!\n ", e)
            return 1
        return int(size)
