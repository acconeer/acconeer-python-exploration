import numpy as np
from numpy import pi
from matplotlib.gridspec import GridSpec
from scipy.signal import butter, sosfilt

from acconeer_utils.clients.reg.client import RegClient
from acconeer_utils.clients.json.client import JSONClient
from acconeer_utils.clients import configs
from acconeer_utils import example_utils
from acconeer_utils.mpl_process import PlotProcess, PlotProccessDiedException, FigureUpdater


env_max = 0.3
hist_plot_len = 800


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

    processor = BreathingProcessor(config)

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
    config.range_interval = [0.18, 0.60]
    config.sweep_rate = 50
    config.gain = 0.7
    return config


class BreathingProcessor:
    breath_hist_len = 2000
    pulse_hist_len = 800
    peak_hist_len = 600

    phase_weights_alpha = 0.9
    peak_loc_alpha = 0.95
    sweep_alpha = 0.7
    env_alpha = 0.95

    def __init__(self, config):
        self.config = config
        self.hist_plot_len = hist_plot_len

        self.f = config.sweep_rate

        self.peak_history = np.zeros(self.peak_hist_len, dtype="complex")
        self.movement_history = np.zeros(self.peak_hist_len, dtype="float")
        self.breath_history = np.zeros(self.breath_hist_len, dtype="float")
        self.pulse_history = np.zeros(self.pulse_hist_len, dtype="float")

        self.breath_sos = np.concatenate(butter(2, 2 * 0.3/self.f))
        self.breath_zi = np.zeros((1, 2))
        self.pulse_sos = np.concatenate(butter(2, 2 * np.array([5])/self.f))
        self.pulse_zi = np.zeros((1, 2))

        self.last_lp_sweep = None
        self.lp_phase_weights = None
        self.lp_sweep = None
        self.lp_peak_loc = 0

        self.sweep_index = 0

    def process(self, sweep):
        if self.sweep_index == 0:
            self.lp_sweep = np.array(sweep)
            self.lp_env = np.abs(sweep)
            self.lp_peak_loc = np.argmax(self.lp_env)

            out_data = None
        else:
            self.lp_sweep = self.lp(sweep, self.lp_sweep, self.sweep_alpha)
            env = np.abs(self.lp_sweep)
            self.lp_env = self.lp(env, self.lp_env, self.env_alpha)
            peak_loc = np.argmax(self.lp_env)
            self.lp_peak_loc = self.lp(peak_loc, self.lp_peak_loc, self.peak_loc_alpha)

            peak_idx = int(round(self.lp_peak_loc))
            peak = np.mean(self.lp_sweep[peak_idx-50:peak_idx+50])
            self.push(peak, self.peak_history)

            delta = self.lp_sweep * np.conj(self.last_lp_sweep)

            phase_weights = np.imag(delta)
            if self.lp_phase_weights is None:
                self.lp_phase_weights = phase_weights
            else:
                self.lp_phase_weights = self.lp(
                        phase_weights,
                        self.lp_phase_weights,
                        self.phase_weights_alpha
                        )

            weights = np.abs(self.lp_phase_weights) * (env/env_max)

            delta_dist = np.dot(weights, np.angle(delta))
            delta_dist *= 2.5 / (2.0 * pi * sum(weights + 0.00001))

            y = self.movement_history[0] + delta_dist
            self.push(y, self.movement_history)

            y_breath, self.breath_zi = sosfilt(self.breath_sos, np.array([y]), zi=self.breath_zi)
            self.push(y_breath, self.breath_history)

            y_pulse, self.pulse_zi = sosfilt(self.pulse_sos, np.array([y]), zi=self.pulse_zi)
            self.push(y_pulse, self.pulse_history)

            env_delta = 10*self.lp_phase_weights + 0.5*env_max

            maxs = self.find_peaks(self.breath_history, 100)
            mins = self.find_peaks(-self.breath_history, 100)
            max_idx = 0
            min_idx = 0
            inhale_time = None
            exhale_time = None
            inhale_dist = 0
            exhale_dist = 0
            exhale = None
            first_peak = None
            while not (inhale_time and exhale_time):
                if not (min_idx < mins.shape[0] and max_idx < maxs.shape[0]):
                    break

                if maxs[max_idx, 0] < mins[min_idx, 0]:
                    exhale_dist = mins[min_idx, 1] + maxs[max_idx, 1]
                    if (exhale_dist > 1 and exhale_dist < 20):
                        exhale_time = mins[min_idx, 0] - maxs[max_idx, 0]
                        if first_peak is None:
                            first_peak = maxs[max_idx, 0]
                        exhale = True
                    max_idx += 1
                else:
                    inhale_dist = mins[min_idx, 1] + maxs[max_idx, 1]
                    if (inhale_dist > 1 and inhale_dist < 20):
                        inhale_time = maxs[max_idx, 0]-mins[min_idx, 0]
                        exhale = False
                        if first_peak is None:
                            first_peak = mins[min_idx, 0]
                    min_idx += 1

            breathing = False
            if inhale_time is not None and exhale_time is not None:
                bpm = 60.0 / ((inhale_time + exhale_time) / self.f)
                symmetry = (inhale_dist - exhale_dist) / (inhale_dist + exhale_dist)
                first_peak_rel = first_peak / (inhale_time + exhale_time)
                if 3 < bpm < 30 and abs(symmetry) < 0.5 and first_peak_rel < 0.7:
                    breathing = True

            if breathing:
                bstr = "Exhaling" if exhale else "Inhaling"
                bpm_text = "{}, BPM {:0.1f}, depth {:0.1f} mm".format(bstr, bpm, inhale_dist)
            else:
                bpm_text = "No breathing detected"

            # Make an explicit copy, otherwise flip will not return a new object
            breath_hist_plot = np.array(np.flip(self.breath_history[:self.hist_plot_len], axis=0))
            breath_hist_plot -= (np.max(breath_hist_plot) + np.min(breath_hist_plot)) * 0.5

            zoom_hist_plot = np.array(np.flip(self.pulse_history[:self.hist_plot_len], axis=0))
            zoom_hist_plot -= (max(zoom_hist_plot) + min(zoom_hist_plot)) * 0.5

            out_data = {
                "peak_hist": self.peak_history[:100],
                "peak_std_mm": 2.5 * np.std(np.unwrap(np.angle(self.peak_history)))/2.0/pi,
                "env_ampl": abs(self.lp_sweep),
                "env_delta": env_delta,
                "peak_idx": peak_idx,
                "breathing_history": breath_hist_plot,
                "breathing_text": bpm_text,
                "zoom_hist": zoom_hist_plot,
            }

        self.last_lp_sweep = self.lp_sweep
        self.sweep_index += 1
        return out_data

    def lp(self, new, state, alpha):
        return alpha*state + (1-alpha)*new

    def push(self, val, arr):
        res = np.empty_like(arr)
        res[0] = val
        res[1:] = arr[:-1]
        arr[...] = res

    def find_peaks(self, env, width):
        n = len(env)
        peaks = np.zeros((0, 2))
        for idx in range(0, n, width):
            mi = np.argmax(env[idx:min(idx+width, n)])+idx
            mi2 = np.argmax(env[max(mi-width, 0):min(mi+width, n)])
            mi2 += max(mi - width, 0)
            if mi == mi2 and (0 < mi < n-1):
                peaks = np.concatenate((peaks, np.array([[mi, env[mi]]])), axis=0)
        return peaks


class ExampleFigureUpdater(FigureUpdater):
    def __init__(self, config):
        self.config = config
        self.hist_plot_len = hist_plot_len

        self.plot_index = 0

    def setup(self, fig):
        fig.set_size_inches(8, 8)

        gs = GridSpec(2, 2)

        self.peak_ax = fig.add_subplot(gs[0, 0])
        self.peak_ax.grid(True)
        self.peak_ax.set_xlim(-env_max, env_max)
        self.peak_ax.set_ylim(-env_max, env_max)
        self.peak_ax.set_title("IQ at peak")

        self.env_ax = fig.add_subplot(gs[0, 1])
        self.env_ax.grid(True)
        self.env_ax.set_xlim(*self.config.range_interval)
        self.env_ax.set_ylim(0, env_max)
        self.env_ax.set_xlabel("Distance (m)")
        self.env_ax.set_title("Envelope and delta")

        self.movement_ax = fig.add_subplot(gs[1, 0])
        self.movement_ax.set_xlim(0, self.hist_plot_len)
        self.movement_ax.set_ylim(-10, 10)
        self.movement_ax.set_xticks([])
        self.movement_ax.set_title("Breathing movement")
        self.movement_ax.set_ylabel("Movement (mm)")

        self.zoom_ax = fig.add_subplot(gs[1, 1])
        self.zoom_ax.set_xlim(0, self.hist_plot_len)
        self.zoom_ax.set_ylim(-1, 1)
        self.zoom_ax.set_xticks([])
        self.zoom_ax.set_yticks([])
        self.zoom_ax.set_title("Relative movement (auto zoom)")

        fig.canvas.set_window_title("Acconeer breathing example")
        fig.tight_layout()

    def first(self, data):
        self.process_data(data)

        self.artists = {}

        self.artists["peak_hist"] = self.peak_ax.plot(self.peak_hist_re, self.peak_hist_im)[0]
        self.artists["peak"] = self.peak_ax.plot(self.peak_re, self.peak_im, "ko", ms=10)[0]
        self.artists["peak_std_text"] = self.peak_ax.text(
                -0.95*env_max,
                -0.95*env_max,
                self.peak_std_text
                )

        self.artists["env_ampl"] = self.env_ax.plot(self.env_xs, data["env_ampl"])[0]
        self.artists["env_delta"] = self.env_ax.plot(self.env_xs, data["env_delta"])[0]
        self.artists["env_peak_vline"] = self.env_ax.axvline(self.peak_x, color="k", ls=":")

        hist_text_plot_x = self.hist_plot_len // 20

        self.artists["rel_dist_hist"] = self.movement_ax.plot(data["breathing_history"])[0]
        self.artists["rel_dist_text"] = self.movement_ax.text(
                hist_text_plot_x,
                -9,
                data["breathing_text"],
                va="center",
                ha="left",
                )

        self.artists["zoom"] = self.zoom_ax.plot(self.zoom_ys)[0]
        zoom_text_y = 0.92
        self.artists["zoom_max_text"] = self.zoom_ax.text(
                hist_text_plot_x,
                zoom_text_y,
                self.zoom_max_text,
                va="center",
                ha="left",
                )
        self.artists["zoom_min_text"] = self.zoom_ax.text(
                hist_text_plot_x,
                -zoom_text_y,
                self.zoom_min_text,
                va="center",
                ha="left",
                )

        return self.artists.values()

    def update(self, data):
        self.process_data(data)

        self.artists["peak_hist"].set_data(self.peak_hist_re, self.peak_hist_im)
        self.artists["peak"].set_data(self.peak_re, self.peak_im)
        self.artists["peak_std_text"].set_text(self.peak_std_text)

        self.artists["env_ampl"].set_ydata(data["env_ampl"])
        self.artists["env_delta"].set_ydata(data["env_delta"])
        self.artists["env_peak_vline"].set_xdata(self.peak_x)

        self.artists["rel_dist_hist"].set_ydata(data["breathing_history"])
        self.artists["rel_dist_text"].set_text(data["breathing_text"])

        self.artists["zoom"].set_ydata(self.zoom_ys)
        self.artists["zoom_max_text"].set_text(self.zoom_max_text)
        self.artists["zoom_min_text"].set_text(self.zoom_min_text)

    def process_data(self, data):
        if self.plot_index == 0:
            self.env_xs = np.linspace(*self.config.range_interval, data["env_ampl"].size)

        self.peak_hist_re = np.real(data["peak_hist"])
        self.peak_hist_im = np.imag(data["peak_hist"])
        self.peak_re = self.peak_hist_re[0]
        self.peak_im = self.peak_hist_im[0]
        self.peak_std_text = "Std: {:.3f}mm".format(data["peak_std_mm"])

        self.peak_x = self.env_xs[data["peak_idx"]]

        zoom_lim = max(0.1, max(data["zoom_hist"]) * 1.2)
        self.zoom_ys = data["zoom_hist"] / zoom_lim
        zoom_lim_text = "{:.2f}mm".format(zoom_lim)
        self.zoom_max_text = zoom_lim_text
        self.zoom_min_text = "-" + zoom_lim_text

        self.plot_index += 1


if __name__ == "__main__":
    main()
