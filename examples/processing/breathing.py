import numpy as np
from numpy import pi
from scipy.signal import butter, sosfilt
import pyqtgraph as pg
from PyQt5 import QtCore

from acconeer_utils.clients.reg.client import RegClient
from acconeer_utils.clients.json.client import JSONClient
from acconeer_utils.clients import configs
from acconeer_utils import example_utils
from acconeer_utils.pg_process import PGProcess, PGProccessDiedException


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

    pg_updater = PGUpdater(config)
    pg_process = PGProcess(pg_updater)
    pg_process.start()

    client.start_streaming()

    interrupt_handler = example_utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    processor = BreathingProcessor(config)

    while not interrupt_handler.got_signal:
        info, sweep = client.get_next()
        plot_data = processor.process(sweep)

        if plot_data is not None:
            try:
                pg_process.put_data(plot_data)
            except PGProccessDiedException:
                break

    print("Disconnecting...")
    pg_process.close()
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


class PGUpdater:
    def __init__(self, config):
        self.config = config
        self.move_xs = (np.arange(-hist_plot_len, 0) + 1) / self.config.sweep_rate
        self.plot_index = 0

    def setup(self, win):
        win.setWindowTitle("Acconeer breathing example")
        win.resize(800, 600)

        self.peak_plot = win.addPlot(title="IQ at peak")
        example_utils.pg_setup_polar_plot(self.peak_plot, 0.3)
        self.peak_curve = self.peak_plot.plot(pen=example_utils.pg_pen_cycler(0))
        self.peak_scatter = pg.ScatterPlotItem(brush=pg.mkBrush("k"), size=15)
        self.peak_plot.addItem(self.peak_scatter)
        self.peak_text_item = pg.TextItem(color=pg.mkColor("k"), anchor=(0, 1))
        self.peak_plot.addItem(self.peak_text_item)
        self.peak_text_item.setPos(-0.3*1.15, -0.3*1.15)

        self.env_plot = win.addPlot(title="Envelope and delta")
        self.env_plot.showGrid(x=True, y=True)
        self.env_plot.setYRange(0, 0.3)
        self.env_curve = self.env_plot.plot(pen=example_utils.pg_pen_cycler(0))
        self.delta_curve = self.env_plot.plot(pen=example_utils.pg_pen_cycler(1))
        self.peak_vline = pg.InfiniteLine(pen=pg.mkPen("k", width=2.5, style=QtCore.Qt.DashLine))
        self.env_plot.addItem(self.peak_vline)

        win.nextRow()
        self.move_plot = win.addPlot(title="Breathing movement")
        self.move_plot.showGrid(x=True, y=True)
        self.move_plot.setLabel("bottom", "Time (s)")
        self.move_plot.setLabel("left", "Movement (mm)")
        self.move_plot.setYRange(-10, 10)
        self.move_curve = self.move_plot.plot(pen=example_utils.pg_pen_cycler(0))
        self.move_text_item = pg.TextItem(color=pg.mkColor("k"), anchor=(0, 1))
        self.move_text_item.setPos(self.move_xs[0], -10)
        self.move_plot.addItem(self.move_text_item)

        self.zoom_plot = win.addPlot(title="Relative movement")
        self.zoom_plot.showGrid(x=True, y=True)
        self.zoom_plot.setLabel("bottom", "Time (s)")
        self.zoom_plot.setLabel("left", "Movement (mm)")
        self.zoom_curve = self.zoom_plot.plot(pen=example_utils.pg_pen_cycler(0))

    def update(self, data):
        self.process_data(data)

        self.peak_scatter.setData([self.peak_re], [self.peak_im])
        self.peak_curve.setData(self.peak_hist_re, self.peak_hist_im)
        self.peak_text_item.setText(self.peak_std_text)
        self.env_curve.setData(self.env_xs, data["env_ampl"])
        self.delta_curve.setData(self.env_xs, data["env_delta"])
        self.peak_vline.setValue(self.peak_x)
        self.move_curve.setData(self.move_xs, data["breathing_history"])
        self.zoom_curve.setData(self.move_xs, data["zoom_hist"])
        self.move_text_item.setText(data["breathing_text"])

    def process_data(self, data):
        if self.plot_index == 0:
            self.env_xs = np.linspace(*self.config.range_interval, data["env_ampl"].size)

        self.peak_hist_re = np.real(data["peak_hist"])
        self.peak_hist_im = np.imag(data["peak_hist"])
        self.peak_re = self.peak_hist_re[0]
        self.peak_im = self.peak_hist_im[0]
        self.peak_std_text = "Std: {:.3f}mm".format(data["peak_std_mm"])
        self.peak_x = self.env_xs[data["peak_idx"]]
        self.plot_index += 1


if __name__ == "__main__":
    main()
