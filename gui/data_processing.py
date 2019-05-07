import numpy as np
import time

import warnings
warnings.filterwarnings("ignore")


def get_internal_processing_config():
    return {
        "image_buffer": {
            "name": "Image history",
            "value": 100,
            "limits": [10, 16384],
            "type": int,
            "text": None,
        },
        "averging": {
            "name": "Averaging",
            "value": 0,
            "limits": [0, 0.9999],
            "type": float,
            "text": None,
        },
    }


def get_sparse_processing_config():
    return {
        "image_buffer": {
            "name": "Image history",
            "value": 100,
            "limits": [10, 16384],
            "type": int,
            "text": None,
        },
    }


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
        self.cl_file = params["clutter_file"]
        self.sweeps = parent.parent.sweep_count
        self.rate = 1/params["sensor_config"].sweep_rate
        self.hist_len = params["sweep_buffer"]
        self.service_params = params["service_params"]

        self.image_buffer = 0
        if self.service_type.lower() in ["iq", "envelope", "sparse"]:
            self.image_buffer = params["service_params"]["image_buffer"]["value"]

        if self.sweeps < 0:
            self.sweeps = self.hist_len

        if self.create_cl:
            parent.sweep_count = min(self.sweeps, parent.sweep_count)

        self.parent = parent
        self.hist_len_index = 0

        self.init_vars()

    def get_processing_type(self, service):
        process = self.external_processing
        if self.service_type.lower() in ["iq", "envelope"]:
            process = self.internal_processing
        elif service.lower() == "power bin":
            process = self.power_bin_processing
        elif service.lower() == "sparse":
            process = self.sparse_processing
        return process

    def abort_processing(self):
        self.abort = True

    def init_vars(self):
        self.peak_history = np.zeros(self.image_buffer, dtype="float")
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

    def set_clutter_flag(self, enable):
        self.use_cl = enable

    def load_clutter_data(self, cl_length, cl_file=None):
        load_success = True
        error = None

        if cl_file:
            try:
                cl_data = np.load(cl_file, allow_pickle=True)
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
                if not np.isclose(cl_config.gain, self.sensor_config.gain):
                    load_success = False
                    error = "Wrong gain:\n Clutter is {} and scan is {}".format(
                        cl_config.gain, self.sensor_config.gain)
                if not np.isclose(cl_config.range_interval,
                                  self.sensor_config.range_interval).any():
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
            self.use_cl = False
            if error:
                try:
                    error += "\nFile: {:s}\n".format(cl_file)
                except Exception:
                    pass
                self.parent.emit("clutter_error", error)

        return (cl, cl_iq, thrshld)

    def power_bin_processing(self, iq_data, info):
        if not self.sweep:
            self.env_x_mm = np.linspace(self.start_x, self.stop_x, iq_data.size)*1000

        plot_data = {
            "iq_data": iq_data,
            "sensor_config": self.sensor_config,
            "sweep": self.sweep,
            "x_mm": self.env_x_mm,
        }

        self.record_data(iq_data, info)
        self.draw_canvas(self.sweep, plot_data, "update_power_plots")
        self.sweep += 1

        return (plot_data, self.record)

    def sparse_processing(self, iq_data, info):
        num_subsweeps = iq_data.shape[0]
        if not self.sweep:
            self.env_x_mm = np.tile(np.linspace(self.start_x, self.stop_x, iq_data.shape[1]),
                                    num_subsweeps) * 1000
            self.hist_env = np.zeros((self.image_buffer, iq_data.shape[1]))
            self.gamma_map = np.zeros((self.image_buffer, iq_data.shape[1]))
            self.plus = np.zeros((self.image_buffer, iq_data.shape[1]))
            self.minus = np.zeros((self.image_buffer, iq_data.shape[1]))

            f = self.sensor_config.sweep_rate

            self.move_hist = np.zeros((self.image_buffer, iq_data.shape[1]))

            upper_speed_limit = 25
            self.a_fast_tau = 1.0 / (upper_speed_limit / 2.5)
            self.a_slow_tau = 1.0
            self.a_move_tau = 0.2
            self.a_fast = self.alpha(self.a_fast_tau, 1.0 / (f * num_subsweeps))
            self.a_slow = self.alpha(self.a_slow_tau, 1.0 / (f * num_subsweeps))
            self.a_move = self.alpha(self.a_move_tau, 1.0 / (f * num_subsweeps))
            self.movement_lp = 0
            self.lp_fast = None

        #  Create average envelope history
        self.plus.fill(0)
        self.minus.fill(0)
        avg_env = np.mean(iq_data, axis=0)
        self.hist_env = np.roll(self.hist_env, 1, axis=0)
        self.hist_env[0, :] = avg_env

        self.plus[self.hist_env >= 0] = self.hist_env[self.hist_env >= 0] / 2**15 * 254
        self.minus[self.hist_env <= 0] = -self.hist_env[self.hist_env <= 0] / 2**15 * 254

        self.gamma(self.plus)
        self.gamma(self.minus)

        self.gamma_map[self.hist_env >= 0] = 254 + self.plus[self.hist_env >= 0]
        self.gamma_map[self.hist_env < 0] = 254 - self.minus[self.hist_env < 0]

        self.gamma_map /= 2

        #  Create movement history
        for subsweep in iq_data:
            if self.lp_fast is None:
                self.lp_fast = subsweep.copy()
                self.lp_slow = subsweep.copy()
            else:
                self.lp_fast = self.lp_fast * self.a_fast + subsweep * (1 - self.a_fast)
                self.lp_slow = self.lp_slow * self.a_slow + subsweep * (1 - self.a_slow)

                move = np.abs(self.lp_fast - self.lp_slow)
                self.movement_lp = self.movement_lp * self.a_move + move * (1 - self.a_move)

        self.move_hist = np.roll(self.move_hist, 1, axis=0)
        self.move_hist[0, :] = self.movement_lp

        plot_data = {
            "iq_data": iq_data.flatten(),
            "hist_env": self.gamma_map.copy(),
            "hist_move": self.move_hist,
            "sensor_config": self.sensor_config,
            "sweep": self.sweep,
            "x_mm": self.env_x_mm,
        }

        self.record_data(iq_data, info)
        self.draw_canvas(self.sweep, plot_data, "update_sparse_plots")
        self.sweep += 1

        return (plot_data, self.record)

    def alpha(self, tau, dt):
        return np.exp(-dt/tau)

    def internal_processing(self, iq_data, info):
        complex_env = None

        snr = {}
        peak_data = {}

        if self.sweep == 0:
            self.cl_empty = np.zeros(len(iq_data))
            self.cl, self.cl_iq, self.n_std_avg = \
                self.load_clutter_data(len(iq_data), self.cl_file)
            self.env_x_mm = np.linspace(self.start_x, self.stop_x, iq_data.size)*1000
            self.hist_env = np.zeros((len(self.env_x_mm), self.image_buffer))

        complex_env = iq_data.copy()
        if self.use_cl:
            # For envelope mode cl_iq is amplitude only
            try:
                complex_env = iq_data - self.cl_iq
                if "iq" not in self.mode:
                    complex_env[complex_env < 0] = 0
            except Exception as e:
                self.parent.emit("error", "Background has wrong format!\n{}".format(e))
                self.cl_iq = self.cl = np.zeros((len(complex_env)))

        time_filter = self.service_params["averging"]["value"]
        if time_filter >= 0:
            if self.sweep < np.ceil(1.0 / (1.0 - self.service_params["averging"]["value"]) - 1):
                time_filter = min(1.0 - 1.0 / (self.sweep + 1), time_filter)
            if self.sweep:
                complex_env = (1 - time_filter) * complex_env + time_filter * self.last_complex_env
            self.last_complex_env = complex_env.copy()

        env = np.abs(complex_env)

        if self.create_cl:
            if self.sweep == 0:
                self.cl = np.zeros((self.sweeps, len(env)))
                self.cl_iq = np.zeros((self.sweeps, len(env)), dtype="complex")
            self.cl[self.sweep, :] = env
            self.cl_iq[self.sweep, :] = iq_data

        env_peak_idx = np.argmax(env)

        phase = np.angle(np.mean(complex_env[(env_peak_idx-50):(env_peak_idx+50)]))

        peak_mm = self.env_x_mm[env_peak_idx]
        if peak_mm <= self.start_x * 1000:
            peak_mm = self.stop_x * 1000

        hist_plot = np.flip(self.peak_history, axis=0)
        self.peak_history = np.roll(self.peak_history, 1)
        self.peak_history[0] = peak_mm

        self.hist_env = np.roll(self.hist_env, 1, axis=1)
        self.hist_env[:, 0] = env

        std_len = min(self.sweep, len(self.peak_history) - 1)

        peak_data = {
            "peak_mm": peak_mm,
            "std_peak_mm": np.std(self.peak_history[0:min(self.sweep, std_len)]),
        }

        snr = None
        signal = np.abs(env)[env_peak_idx]
        if self.use_cl and self.n_std_avg[env_peak_idx] > 0:
            noise = self.n_std_avg[env_peak_idx]
            snr = 20*np.log10(signal / noise)
        else:
            # Simple noise estimate: noise ~ mean(envelope)
            noise = np.mean(env)
            snr = 20*np.log10(signal / noise)

        phase = np.angle(complex_env)
        phase /= np.max(np.abs(phase))

        self.env_max = np.max(env)

        cl = self.cl
        cl_iq = self.cl_iq
        if self.create_cl:
            cl = self.cl[self.sweep, :]
            cl_iq = self.cl_iq[self.sweep, :]
        elif not self.use_cl:
            cl = self.cl_empty
            cl_iq = self.cl_empty

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
            "cl_file": self.cl_file,
            "sweep": self.sweep,
            "snr": snr,
            "phase": phase,
        }

        self.record_data(iq_data, info)
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

    def external_processing(self, sweep_data, info):
        if self.first_run:
            self.external = self.parent.parent.external(self.sensor_config, self.service_params)
            self.first_run = False
            self.service_widget = self.parent.parent.service_widget
            plot_data = self.external.process(sweep_data)
        else:
            plot_data = self.external.process(sweep_data)
            if plot_data:
                self.draw_canvas(self.sweep, plot_data, "update_external_plots")
                self.sweep += 1
            if plot_data.get("send_process_data") is not None:
                self.parent.emit("process_data", "", plot_data["send_process_data"])

        self.record_data(sweep_data, info)
        return None, self.record

    def record_data(self, sweep_data, info):
        plot_data = {
            "service_type": self.service_type,
            "sweep_data": sweep_data,
            "sensor_config": self.sensor_config,
            "cl_file": self.cl_file,
            "info": info,
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

        info_available = True
        try:
            self.sweeps = len(data)
        except Exception as e:
            self.parent.emit("error", "Wrong file format\n {}".format(e))
            return

        try:
            sequence_offset = max(data[0]["info"]["sequence_number"] - 1, 0)
        except Exception:
            info_available = False

        if not info_available:
            self.info = {"sequence_number": 1}
            print("Session info not available")

        for i, data_step in enumerate(data):
            if info_available:
                info = data[i]["info"]
                info["sequence_number"] -= sequence_offset
            else:
                info = self.info.copy()
            if not self.abort:
                self.skip = 0
                time.sleep(self.rate)
                plot_data, _ = self.process(data_step["sweep_data"], info)

                self.parent.emit("sweep_info", "", info)

            if not info_available:
                self.info["sequence_number"] += 1

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

    def gamma(self, arr, alpha=2.2, max_brightness=254, min_brightness=50):
        g = 1/alpha
        map_max = max(np.max(np.max(arr)), min_brightness)
        gamma_map = max_brightness/map_max**g * arr**g

        gamma_map[gamma_map > max_brightness] = max_brightness

        arr[...] = gamma_map
