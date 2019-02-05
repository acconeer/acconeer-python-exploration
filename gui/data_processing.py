import numpy as np
import time

import warnings
warnings.filterwarnings("ignore")


class DataProcessing:
    hist_len = 500

    def prepare_processing(self, parent, params):
        self.sensor_config = params["sensor_config"]
        self.mode = self.sensor_config.mode
        self.service_type = params["service_type"]
        self.start_x = self.sensor_config.range_interval[0]
        self.stop_x = self.sensor_config.range_interval[1]
        self.create_cl = params["create_clutter"]
        self.use_cl = params["use_clutter"]
        self.sweeps = parent.parent.sweep_count
        self.rate = 1/params["sensor_config"].sweep_rate
        self.hist_len = params["sweep_buffer"]

        if self.sweeps < 0:
            self.sweeps = self.hist_len

        if self.create_cl:
            parent.sweep_count = min(self.sweeps, parent.sweep_count)

        self.parent = parent
        self.hist_len_index = 0

        self.init_vars()

    def get_processing_type(self, service):
        process = self.external_processing
        if "iq" in service.lower() or "envelope" in service.lower():
            process = self.internal_processing
        if "power" in service.lower():
            process = self.power_bin_processing
        return process

    def abort_processing(self):
        self.abort = True

    def init_vars(self):
        hist_len = min(self.sweeps, self.hist_len)
        self.peak_history = np.zeros(hist_len, dtype="float")
        self.peak_thrshld_history = np.zeros(hist_len, dtype="float")
        self.hist_plot_len = hist_len
        self.sweep = 0
        self.record = []
        self.env_ampl_avg = 0
        self.complex_avg = 0
        self.n_std_avg = 0
        self.abort = False
        self.env_max = 0
        self.first_run = True
        self.skip = 0

        self.cl = np.zeros((0, 1))
        self.cl_iq = np.zeros((0, 1), dtype="complex")
        self.threshold = np.zeros((0, 1))
        self.process = self.get_processing_type(self.service_type)

    def load_clutter_data(self, cl_length, cl_file=None):
        load_success = True
        error = None

        if cl_file:
            try:
                cl_data = np.load(cl_file)
            except Exception as e:
                error = "Cannot load clutter ({})\n\n{}".format(cl_file, e)
                load_success = False
        else:
            load_success = False

        if load_success:
            try:
                cl = cl_data.item()["cl_env"]
                cl_iq = cl_data.item()["cl_iq"]
                thrshld = cl_data.item()["cl_env_std"]
                cl_config = cl_data.item()["config"]
                if cl_config.gain != self.sensor_config.gain:
                    load_success = False
                    error = "Wrong gain:\n Clutter is {} and scan is {}".format(
                        cl_config.gain, self.sensor_config.gain)
                if (cl_config.range_interval != self.sensor_config.range_interval).any():
                    error = "Wrong range:\n Clutter is {} and scan is {}".format(
                        cl_config.range_interval, self.sensor_config.range_interval)
                if cl_config.mode != self.sensor_config.mode:
                    error = "Wrong modes:\n Clutter is {} and scan is {}".format(
                        cl_config.mode, self.sensor_config.mode)
                if error:
                    load_success = False
            except Exception as e:
                error = "Error loading clutter:\n {}".format(self.parent.format_error(e))
                load_success = False

        if not load_success:
            cl = np.zeros(cl_length)
            thrshld = cl
            cl_iq = cl
            if error:
                self.parent.emit("error", error)

        return (cl, cl_iq, thrshld)

    def power_bin_processing(self, iq_data):
        if not self.sweep:
            self.env_x_mm = np.linspace(self.start_x, self.stop_x, iq_data.size)*1000

        plot_data = {
            "iq_data": iq_data,
            "sensor_config": self.sensor_config,
            "sweep": self.sweep,
            "x_mm": self.env_x_mm,
        }

        self.record_data(iq_data)
        self.draw_canvas(self.sweep, plot_data, "update_power_plots")
        self.sweep += 1

        return (plot_data, self.record)

    def internal_processing(self, iq_data):
        complex_env = None

        snr = {}
        peak_data = {}

        if self.sweep == 0:
            self.cl, self.cl_iq, self.threshold = \
                self.load_clutter_data(len(iq_data), self.use_cl)
            self.cl = np.abs(self.cl_iq)
            self.env_x_mm = np.linspace(self.start_x, self.stop_x, iq_data.size)*1000

        complex_env = iq_data
        if self.use_cl and self.sweep:
            complex_env = iq_data - self.cl_iq

        env = np.abs(complex_env)

        if self.create_cl:
            if self.sweep == 0:
                self.cl = np.zeros((self.sweeps, len(env)))
                self.cl_iq = np.zeros((self.sweeps, len(env)), dtype="complex")
            self.cl[self.sweep, :] = env
            self.cl_iq[self.sweep, :] = iq_data

        if self.use_cl:
            if "iq" not in self.mode:
                try:
                    env -= 1*self.cl
                except Exception as e:
                    self.parent.emit("error", "Background has wrong format!\n{}".format(e))
                    self.cl = np.zeros((len(env)))

                env[env < 0] = 0

        env_peak_idx = np.argmax(env)

        phase = np.angle(np.mean(complex_env[(env_peak_idx-50):(env_peak_idx+50)]))

        peak_mm = self.env_x_mm[env_peak_idx]
        if peak_mm <= self.start_x * 1000:
            peak_mm = self.stop_x * 1000

        try:
            peak_mm_thrshld = self.env_x_mm[np.where((env - self.threshold) >= 0)[0][0]]
        except Exception:
            peak_mm_thrshld = self.env_x_mm[-1]

        hist_plot = np.flip(self.peak_history, axis=0)

        self.peak_history = push(peak_mm, self.peak_history)
        self.peak_thrshld_history = push(peak_mm_thrshld, self.peak_thrshld_history)

        if self.sweep:
            self.env_ampl_avg += env/self.sweeps
            self.complex_avg += complex_env/self.sweeps
            self.n_std_avg += self.threshold/self.sweeps
        else:
            self.env_ampl_avg = env/self.sweeps
            self.complex_avg = complex_env/self.sweeps
            self.n_std_avg = self.threshold/self.sweeps

            self.hist_env = np.zeros((len(self.env_x_mm), self.hist_plot_len))

        cl = self.cl
        cl_iq = self.cl_iq
        if self.create_cl:
            cl = self.cl[self.sweep, :]
            cl_iq = self.cl_iq[self.sweep, :]

        self.hist_env = push(env, self.hist_env, axis=1)

        std_len = min(self.sweep, len(self.peak_history) - 1)

        peak_data = {
            "peak_mm": peak_mm,
            "peak_mm_thrshld": peak_mm_thrshld,
            "std_peak_mm": np.std(self.peak_history[0:min(self.sweep, std_len)]),
            "std_peak_mm_thrshld": np.std(self.peak_thrshld_history[0:min(self.sweep, std_len)]),
        }

        snr = None
        if self.use_cl and self.n_std_avg[env_peak_idx] > 0:
            signal = np.abs(complex_env)[env_peak_idx]-cl[env_peak_idx]
            noise = self.n_std_avg[env_peak_idx]
            snr = 20*np.log10(signal / noise)

        phase = np.angle(complex_env)
        phase /= np.max(np.abs(phase))

        self.env_max = max(max(env), self.env_max)

        plot_data = {
            "iq_data": iq_data,
            "complex_data": complex_env,
            "complex_avg": self.complex_avg,
            "env_ampl": env,
            "env_ampl_avg": self.env_ampl_avg,
            "env_clutter": cl,
            "env_max": self.env_max,
            "iq_clutter": cl_iq,
            "n_std_avg": self.n_std_avg,
            "hist_plot": hist_plot,
            "hist_env": self.hist_env,
            "sensor_config": self.sensor_config,
            "SNR": snr,
            "peaks": peak_data,
            "x_mm": self.env_x_mm,
            "cl_file": self.use_cl,
            "sweep": self.sweep,
            "snr": snr,
            "phase": phase,
        }

        self.record_data(iq_data)
        self.draw_canvas(self.sweep, plot_data)
        self.sweep += 1

        if self.create_cl and self.sweep == self.sweeps:
            cl = np.zeros((3, len(self.cl[0])))
            cl[0] = np.mean(self.cl, axis=0)
            cl[2] = np.mean(self.cl_iq, axis=0)

            for i in range(len(self.cl[0])):
                cl[1, i] = np.std(self.cl[:, i])

            cl_data = {
                "cl_env": cl[0],
                "cl_env_std": cl[1],
                "cl_iq": cl[2],
                "config": self.sensor_config,
            }

            self.parent.emit("clutter_data", "", cl_data)

        return (plot_data, self.record)

    def external_processing(self, sweep_data):
        if self.first_run:
            self.external = self.parent.parent.external(self.sensor_config)
            self.first_run = False
            self.service_widget = self.parent.parent.service_widget
            plot_data = self.external.process(sweep_data)
        else:
            plot_data = self.external.process(sweep_data)
            if plot_data:
                self.draw_canvas(self.sweep, plot_data, "update_external_plots")
                self.sweep += 1

        self.record_data(sweep_data)
        return None, self.record

    def record_data(self, sweep_data):
        plot_data = {
            "service_type": self.service_type,
            "sweep_data": sweep_data,
            "sensor_config": self.sensor_config,
            "cl_file": self.use_cl,
        }

        if self.hist_len_index >= self.hist_len:
            self.record.pop(0)
        else:
            self.hist_len_index += 1

        self.record.append(plot_data.copy())

    def process_saved_data(self, data, parent):
        self.parent = parent
        self.init_vars()
        self.sweep = 0
        self.create_cl = False

        if "sweep_data" not in data[0]:
            self.parent.emit("error", "Wrong file format")
            return

        try:
            data_len = len(data)
        except Exception as e:
            self.parent.emit("error", "Wrong file format\n {}".format(e))
            return

        for i, data_step in enumerate(data):
            if i == 0:
                try:
                    self.sensor_config = data_step["sensor_config"]
                    self.mode = self.sensor_config.mode
                    self.sweeps = data_len
                    self.start_x = self.sensor_config.range_interval[0]
                    self.stop_x = self.sensor_config.range_interval[1]
                    self.use_cl = data_step["cl_file"]
                    service = data_step["service_type"]
                    self.process = self.get_processing_type(service)
                except Exception as e:
                    self.parent.emit("error", "Could not load data\n {}".format(e))
                    return

            if not self.abort:
                if "sleep" in self.service_type.lower():
                    time.sleep(0.001)
                elif "power" in self.service_type.lower():
                    time.sleep(self.rate)
                else:
                    self.skip = 0
                plot_data, _ = self.process(data_step["sweep_data"])

    def draw_canvas(self, sweep_index, plot_data, cmd="update_plots",
                    skip_frames=False):
        if not skip_frames:
            self.update_plots(plot_data, cmd=cmd)
            return

        if self.skip <= 1:
            if sweep_index == 0:
                self.time = time.time()
            self.update_plots(plot_data, cmd=cmd)
            rate = time.time() - self.time
            self.time = time.time()
            self.skip = rate / self.rate
            if self.skip > 1:
                self.skip = np.ceil(self.skip)
        else:
            self.skip -= 1
            if self.skip <= 1:
                self.time = time.time()

    def update_plots(self, plot_data, cmd="update_plots"):
        self.parent.emit(cmd, "", plot_data)


def push(val, arr, axis=0):
    res = np.empty_like(arr)
    if axis == 0:
        res[0] = val
        res[1:] = arr[:-1]
    elif axis == 1:
        res[:, 0] = val
        res[:, 1:] = arr[:, :-1]
    else:
        raise NotImplementedError
    return res
