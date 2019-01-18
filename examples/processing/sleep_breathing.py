import numpy as np
from scipy import signal

from acconeer_utils.clients.reg.client import RegClient
from acconeer_utils.clients.json.client import JSONClient
from acconeer_utils.clients import configs
from acconeer_utils import example_utils
from acconeer_utils.mpl_process import PlotProcess, PlotProccessDiedException, FigureUpdater


def main():
    args = example_utils.ExampleArgumentParser(num_sens=1).parse_args()
    example_utils.config_logging(args)

    if args.socket_addr:
        client = JSONClient(args.socket_addr)
    else:
        port = args.serial_port or example_utils.autodetect_serial_port()
        client = RegClient(port)

    config = get_base_config()
    config.sensor = args.sensors

    client.setup_session(config)

    fig_updater = ExampleFigureUpdater(config)
    plot_process = PlotProcess(fig_updater)
    plot_process.start()

    client.start_streaming()

    interrupt_handler = example_utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    processor = PresenceDetectionProcessor(config)

    while not interrupt_handler.got_signal:
        info, sweep = client.get_next()
        plot_data = processor.process(sweep)

        try:
            plot_process.put_data(plot_data)  # Will ignore the first None from processor
        except PlotProccessDiedException:
            break

    print("Disconnecting...")
    plot_process.close()
    client.disconnect()


def get_base_config():
    config = configs.IQServiceConfig()
    config.range_interval = [0.4, 0.8]
    config.sweep_rate = 60
    config.gain = 0.6
    return config


class PresenceDetectionProcessor:
    def __init__(self, config):
        self.config = config

        # Settings
        n_dft = 15                         # Data length for frequency estimation [s] | 20
        t_freq_est = 0.5                   # Time between frequency estimations [s] | 2
        tau_iq = 0.04                      # Time constant low-pass filter on IQ-data [s] | 0.04
        self.f_s = self.config.sweep_rate  # Time constant low-pass filter on IQ-data [s] | 150
        self.D = 124                       # Spatial or Range down sampling factor | 124
        self.f_low = 0.1                   # Lowest frequency of interest [Hz] | 0.1
        self.f_high = 1.0                  # Highest frequency of interest [Hz] | 1
        self.M = int(self.f_s / 10)        # Time down sampling for DFT | 40 f_s/M ~ 10 Hz
        self.lambda_p = 40                 # Threshold: spectral peak to noise ratio [1] | 50
        self.lamda_05 = 6                  # Threshold: ratio fundamental and half harmonic
        self.interpolate = True            # Interpolation between DFT points

        self.delta_f = 1 / n_dft
        self.dft_f_vec = np.arange(self.f_low, self.f_high, self.delta_f)
        self.dft_points = np.size(self.dft_f_vec)

        # Butterworth bandpass filter
        f_n = self.f_s / 2
        v_low = self.f_low / f_n
        v_high = self.f_high / f_n
        self.b, self.a = signal.butter(4, [v_low, v_high], btype="bandpass")

        # Exponential lowpass filter
        self.alpha_iq = np.exp(-2 / (self.f_s * tau_iq))
        self.alpha_phi = np.exp(-2 * self.f_low / self.f_s)

        # Parameter init
        self.sweeps_in_block = int(np.ceil(n_dft * self.f_s))
        self.new_sweeps_per_results = int(np.ceil(t_freq_est * self.f_s))
        self.phi_vec = np.zeros((self.sweeps_in_block, 1))
        self.f_est_vec = np.zeros(1)
        self.f_dft_est_vec = np.zeros(1)
        self.snr_vec = 0

        self.sweep_index = 0

    def process(self, sweep):
        if self.sweep_index == 0:
            delay_points = int(np.ceil(np.size(sweep) / self.D))
            self.data_s_d_mat = np.zeros((self.sweeps_in_block, delay_points), dtype="complex")
            self.data_s_d_mat[self.sweep_index, :] = self.downsample(sweep, self.D)

            out_data = None
        elif self.sweep_index < self.sweeps_in_block:
            self.data_s_d_mat[self.sweep_index, :] = self.iq_lp_filter_time(
                    self.data_s_d_mat[self.sweep_index - 1, :],
                    self.downsample(sweep, self.D)
                    )

            temp_phi = self.unwrap_phase(
                    self.phi_vec[self.sweep_index - 1],
                    self.data_s_d_mat[self.sweep_index, :],
                    self.data_s_d_mat[self.sweep_index - 1, :]
                    )

            self.phi_vec[self.sweep_index] = self.unwrap_phase(
                    self.phi_vec[self.sweep_index - 1],
                    self.data_s_d_mat[self.sweep_index, :],
                    self.data_s_d_mat[self.sweep_index - 1, :]
                    )

            phi_filt = signal.lfilter(self.b, self.a, self.phi_vec, axis=0)
            phi_filt /= np.max(np.abs(self.phi_vec))

            out_data = {
                "phi_raw": self.phi_vec / np.max(np.absolute(self.phi_vec)),
                "phi_filt": phi_filt,
                "power_spectrum": np.zeros(self.dft_points),
                "x_dft": np.linspace(self.f_low, self.f_high, self.dft_points),
                "f_dft_est_hist": self.f_dft_est_vec,
                "f_est_hist": self.f_est_vec,
                "f_dft_est": 0,
                "f_est": 0,
                "f_low": self.f_low,
                "f_high": self.f_high,
                "snr": 0,
                "lambda_p": self.lambda_p,
                "dist_range": self.config.range_interval,
                "init_progress": round(100 * self.sweep_index / self.sweeps_in_block),
            }
        else:
            # Lowpass filter IQ data downsampled in distance points
            self.data_s_d_mat = np.roll(self.data_s_d_mat, -1, axis=0)
            self.data_s_d_mat[-1, :] = self.iq_lp_filter_time(
                    self.data_s_d_mat[-1, :],
                    self.downsample(sweep, self.D)
                    )

            # Phase unwrapping of IQ data
            temp_phi = self.unwrap_phase(
                    self.phi_vec[-1],
                    self.data_s_d_mat[-1, :],
                    self.data_s_d_mat[-2, :]
                    )
            self.phi_vec = np.roll(self.phi_vec, -1, axis=0)
            self.phi_vec[-1] = temp_phi

            if np.mod(self.sweep_index, self.new_sweeps_per_results - 1) == 0:
                # Bandpass filter unwrapped data
                phi_filt_vec = signal.lfilter(self.b, self.a, self.phi_vec, axis=0)
                P, dft_est, _ = self.dft(self.downsample(phi_filt_vec, self.M))
                f_breath_est, _, snr, _ = self.breath_freq_est(P)

                self.f_est_vec = np.append(self.f_est_vec, f_breath_est)
                self.f_dft_est_vec = np.append(self.f_dft_est_vec, dft_est)
                self.snr_vec = np.append(self.snr_vec, snr)

                out_data = {
                    "phi_raw": self.phi_vec / np.max(np.absolute(self.phi_vec)),
                    "phi_filt": phi_filt_vec / np.max(np.absolute(self.phi_vec)),
                    "power_spectrum": P / np.max(P),
                    "x_dft": np.linspace(self.f_low, self.f_high, self.dft_points),
                    "f_dft_est_hist": self.f_dft_est_vec,
                    "f_est_hist": self.f_est_vec,
                    "f_dft_est": dft_est,
                    "f_est": f_breath_est,
                    "f_low": self.f_low,
                    "f_high": self.f_high,
                    "snr": snr,
                    "lambda_p": self.lambda_p,
                    "dist_range": self.config.range_interval,
                    "init_progress": None,
                }
            else:
                out_data = None

        self.sweep_index += 1
        return out_data

    def downsample(self, data, n):
        return data[::n]

    def iq_lp_filter_time(self, state, new_data):
        return self.alpha_iq * state + (1 - self.alpha_iq) * new_data

    def unwrap_phase(self, phase_lp, data_1, data_2):
        return phase_lp * self.alpha_phi + np.angle(np.mean(data_2 * np.conjugate(data_1)))

    def dft(self, data):
        data = np.squeeze(data)
        n_vec = np.arange(data.size) * self.M
        dft = np.exp((2j * np.pi / self.f_s) * np.outer(self.dft_f_vec, n_vec))
        P = np.square(np.abs(np.matmul(dft, data)))
        idx_f = np.argmax(P)
        dft_est = self.dft_f_vec[idx_f]
        return P, dft_est, P[idx_f]

    def noise_est(self, P):
        return np.mean(np.sort(P)[:(self.dft_points//2)-1])

    def half_peak_frequency(self, P, f_est):
        idx_half = int(f_est / (2 * self.delta_f))
        if idx_half < self.f_low:
            return 0
        else:
            return (1 / self.delta_f) * (
                        (self.dft_f_vec[idx_half+1] - f_est / 2) * P[idx_half]
                        + (f_est/2 - self.dft_f_vec[idx_half]) * P[idx_half + 1]
                    )

    def breath_freq_est(self, P):
        f_idx = np.argmax(P)
        P_peak = P[f_idx]

        if self.interpolate:
            f_est, P_peak = self.freq_quad_interpolation(P)
        else:
            f_est = self.dft_f_vec[f_idx]

        P_half = self.half_peak_frequency(P, f_est)

        if (P_peak < self.lamda_05 * P_half):
            f_est = f_est / 2
            P_peak = P_half

        if self.f_low < f_est < self.f_high and P_peak > self.lambda_p*self.noise_est(P):
            f_est_valid = True
        else:
            f_est_valid = False
            f_est = 0

        snr = P_peak / self.noise_est(P)
        return f_est, P_peak, snr, f_est_valid

    def freq_quad_interpolation(self, P):
        f_idx = np.argmax(P)

        if 0 < f_idx < P.size and P.size > 3:
            f_est = self.dft_f_vec[f_idx] \
                    + self.delta_f / 2 * (
                            (np.log(P[f_idx+1])-np.log(P[f_idx-1]))
                            / (2*np.log(P[f_idx]) - np.log(P[f_idx+1]) - np.log(P[f_idx-1]))
                        )
            P_peak = P[f_idx] + np.exp(
                        1/8 * np.square(np.log(P[f_idx+1]) - np.log(P[f_idx-1]))
                        / (2*np.log(P[f_idx]) - np.log(P[f_idx+1]) - np.log(P[f_idx-1]))
                    )

            if not (self.f_low < f_est < self.f_high):
                f_est = 0
        else:
            f_est = 0
            P_peak = 0

        return f_est, P_peak


class ExampleFigureUpdater(FigureUpdater):
    def __init__(self, config):
        self.config = config

    def setup(self, fig):
        self.phi_ax = fig.add_subplot(3, 1, 1)
        self.phi_ax.set_title("Breathing motion")
        self.phi_ax.set_ylabel("Amplitude")
        self.phi_ax.set_xlabel("Samples used for processing")
        self.phi_ax.set_yticks([])
        self.phi_ax.set_ylim(-1.1, 1.1)

        self.power_spectrum_ax = fig.add_subplot(3, 1, 2)
        self.power_spectrum_ax.set_title("Power spectrum")
        self.power_spectrum_ax.set_ylabel("Amplitude")
        self.power_spectrum_ax.set_xlabel("Frequency (Hz)")
        self.power_spectrum_ax.set_yticks([])
        self.power_spectrum_ax.set_xlim(-0.01, 1.1)
        self.power_spectrum_ax.set_ylim(0, 1.1)

        self.f_est_hist = fig.add_subplot(3, 1, 3)
        self.f_est_hist.set_title("Breathing estimation history")
        self.f_est_hist.set_ylabel("Frequency (Hz)")
        self.f_est_hist.set_xlabel("Breathing estimation samples")
        self.f_est_hist.set_xticks([])
        self.f_est_hist.set_xlim(0, 1.1)
        self.f_est_hist.set_ylim(0, 1.2)

        fig.canvas.set_window_title("Acconeer sleep breathing estimation example")
        fig.set_size_inches(10, 8)
        fig.tight_layout()

    def first(self, data):
        self.artists = {}

        self.phi_ax.set_title(
            "Breathing motion (detection range: {} m to {} m)".format(*self.config.range_interval))

        self.artists["phi_raw"] = self.phi_ax.plot(data["phi_raw"], color="grey")[0]
        self.artists["phi_filt"] = self.phi_ax.plot(data["phi_filt"], color="k")[0]

        self.artists["init_progress"] = self.power_spectrum_ax.text(
                0.5,
                0.5,
                "Initiating... ",
                transform=self.power_spectrum_ax.transAxes,
                size="large",
                ha="center",
                va="center"
                )

        self.artists["power_spectrum"] = self.power_spectrum_ax.plot(
                data["x_dft"],
                data["power_spectrum"],
                color="grey"
                )[0]

        self.artists["f_dft_est"] = self.power_spectrum_ax.axvline(
                data["f_dft_est"],
                color="grey",
                ls="--"
                )

        self.artists["f_est"] = self.power_spectrum_ax.axvline(data["f_est"], color="k", ls="--")

        self.artists["snr"] = self.power_spectrum_ax.text(
                0.90,
                0.92,
                "",
                transform=self.power_spectrum_ax.transAxes,
                size="large",
                ha="center",
                va="center"
                )

        self.artists["f_dft_est_hist"] = self.f_est_hist.plot(
                np.linspace(0, 1, data["f_dft_est_hist"].size),
                data["f_dft_est_hist"], color="grey"
                )[0]

        self.artists["f_est_hist"] = self.f_est_hist.plot(
                np.linspace(0, 1, data["f_est_hist"].size),
                data["f_est_hist"],
                color="k"
                )[0]

        self.artists["f_high"] = self.f_est_hist.axhline(data["f_high"], color="grey", ls=":")
        self.artists["f_low"] = self.f_est_hist.axhline(data["f_low"], color="grey", ls=":")
        self.artists["f_inst"] = self.f_est_hist.text(
                0.5,
                0.92,
                "Frequency: {:.0f} Hz | {:.0f} BPM".format(data["f_est"], data["f_est"]*60),
                transform=self.f_est_hist.transAxes,
                size="large",
                ha="center",
                va="center"
                )

        return self.artists.values()

    def update(self, data):
        if data["init_progress"] is not None:
            self.artists["init_progress"].set_text(
                    "Initiating: {} %".format(data["init_progress"])
                    )

            self.artists["phi_raw"].set_ydata(data["phi_raw"])
            self.artists["phi_filt"].set_ydata(data["phi_filt"])
        else:
            self.artists["init_progress"].set_text("")
            self.artists["phi_raw"].set_ydata(data["phi_raw"])
            self.artists["phi_filt"].set_ydata(data["phi_filt"])

            self.artists["power_spectrum"].set_data(data["x_dft"], data["power_spectrum"])
            self.artists["f_dft_est"].set_xdata(data["f_dft_est"])
            self.artists["f_est"].set_xdata(data["f_est"])

            self.artists["f_dft_est_hist"].set_data(
                    np.linspace(0, 1, data["f_dft_est_hist"].size), data["f_dft_est_hist"])

            self.artists["f_est_hist"].set_data(
                    np.linspace(0, 1, data["f_est_hist"].size), data["f_est_hist"])

            f_est = data["f_est"]
            if f_est > 0:
                s = "Latest frequency estimate: {:.2f} Hz | {:.0f} BPM".format(f_est, f_est*60)
                self.artists["f_inst"].set_text(s)

            snr = data["snr"]
            if snr == 0:
                s = "SNR: N/A | {:.0f} dB".format(10*np.log10(data["lambda_p"]))
                self.artists["snr"].set_text(s)
            else:
                fmt = "SNR: {:.0f} | {:.0f} dB"
                s = fmt.format(10*np.log10(snr), 10*np.log10(data["lambda_p"]))
                self.artists["snr"].set_text(s)


if __name__ == "__main__":
    main()
