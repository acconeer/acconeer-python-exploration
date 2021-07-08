import warnings

import numpy as np
import pyqtgraph as pg
from numpy import pi
from scipy.signal import butter, sosfilt

from PyQt5 import QtCore

import acconeer.exptool as et


def main():
    args = et.utils.ExampleArgumentParser(num_sens=1).parse_args()
    et.utils.config_logging(args)

    if args.socket_addr:
        client = et.SocketClient(args.socket_addr)
    elif args.spi:
        client = et.SPIClient()
    else:
        port = args.serial_port or et.utils.autodetect_serial_port()
        client = et.UARTClient(port)

    sensor_config = get_sensor_config()
    processing_config = get_processing_config()
    sensor_config.sensor = args.sensors

    session_info = client.setup_session(sensor_config)

    pg_updater = PGUpdater(sensor_config, processing_config, session_info)
    pg_process = et.PGProcess(pg_updater)
    pg_process.start()

    client.start_session()

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    processor = BreathingProcessor(sensor_config, processing_config, session_info)

    while not interrupt_handler.got_signal:
        info, data = client.get_next()
        plot_data = processor.process(data, info)

        if plot_data is not None:
            try:
                pg_process.put_data(plot_data)
            except et.PGProccessDiedException:
                break

    print("Disconnecting...")
    pg_process.close()
    client.disconnect()


def get_sensor_config():
    config = et.configs.IQServiceConfig()
    config.range_interval = [0.3, 0.8]
    config.update_rate = 80
    config.gain = 0.5
    config.repetition_mode = et.configs.IQServiceConfig.RepetitionMode.SENSOR_DRIVEN
    return config


class ProcessingConfiguration(et.configbase.ProcessingConfig):
    VERSION = 1

    hist_plot_len = et.configbase.FloatParameter(
        label="Plot length",
        unit="s",
        default_value=10,
        limits=(1, 30),
        decimals=0,
    )


get_processing_config = ProcessingConfiguration


class BreathingProcessor:
    peak_hist_len = 600

    phase_weights_alpha = 0.9
    peak_loc_alpha = 0.95
    sweep_alpha = 0.7
    env_alpha = 0.95

    def __init__(self, sensor_config, processing_config, session_info):
        self.config = sensor_config

        assert sensor_config.update_rate is not None

        self.f = sensor_config.update_rate
        self.hist_plot_len = int(round(processing_config.hist_plot_len * self.f))
        self.breath_hist_len = max(2000, self.hist_plot_len)

        self.peak_history = np.zeros(self.peak_hist_len, dtype="complex")
        self.movement_history = np.zeros(self.peak_hist_len, dtype="float")
        self.breath_history = np.zeros(self.breath_hist_len, dtype="float")
        self.pulse_history = np.zeros(self.hist_plot_len, dtype="float")

        self.breath_sos = np.concatenate(butter(2, 2 * 0.3 / self.f))
        self.breath_zi = np.zeros((1, 2))
        self.pulse_sos = np.concatenate(butter(2, 2 * np.array([5]) / self.f))
        self.pulse_zi = np.zeros((1, 2))

        self.last_lp_sweep = None
        self.lp_phase_weights = None
        self.lp_sweep = None
        self.lp_peak_loc = 0

        self.sweep_index = 0

    def process(self, data, data_info=None):
        if data_info is None:
            warnings.warn(
                "To leave out data_info or set to None is deprecated",
                DeprecationWarning,
                stacklevel=2,
            )

        sweep = data

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
            peak = np.mean(self.lp_sweep[peak_idx - 50 : peak_idx + 50])
            self.push(peak, self.peak_history)

            delta = self.lp_sweep * np.conj(self.last_lp_sweep)

            phase_weights = np.imag(delta)
            if self.lp_phase_weights is None:
                self.lp_phase_weights = phase_weights
            else:
                self.lp_phase_weights = self.lp(
                    phase_weights,
                    self.lp_phase_weights,
                    self.phase_weights_alpha,
                )

            weights = np.abs(self.lp_phase_weights) * env

            delta_dist = np.dot(weights, np.angle(delta))
            delta_dist *= 2.5 / (2.0 * pi * sum(weights + 0.00001))

            y = self.movement_history[0] + delta_dist
            self.push(y, self.movement_history)

            y_breath, self.breath_zi = sosfilt(self.breath_sos, np.array([y]), zi=self.breath_zi)
            self.push(y_breath, self.breath_history)

            y_pulse, self.pulse_zi = sosfilt(self.pulse_sos, np.array([y]), zi=self.pulse_zi)
            self.push(y_pulse, self.pulse_history)

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
                    if exhale_dist > 1 and exhale_dist < 20:
                        exhale_time = mins[min_idx, 0] - maxs[max_idx, 0]
                        if first_peak is None:
                            first_peak = maxs[max_idx, 0]
                        exhale = True
                    max_idx += 1
                else:
                    inhale_dist = mins[min_idx, 1] + maxs[max_idx, 1]
                    if inhale_dist > 1 and inhale_dist < 20:
                        inhale_time = maxs[max_idx, 0] - mins[min_idx, 0]
                        exhale = False
                        if first_peak is None:
                            first_peak = mins[min_idx, 0]
                    min_idx += 1

            breathing = False
            if inhale_time is not None and exhale_time is not None:
                bpm = 60.0 / ((inhale_time + exhale_time) / self.f)
                symmetry = (inhale_dist - exhale_dist) / (inhale_dist + exhale_dist)
                first_peak_rel = first_peak / (inhale_time + exhale_time)
                if 3 < bpm < 30 and abs(symmetry) < 0.6 and first_peak_rel < 0.7:
                    breathing = True

            if breathing:
                bstr = "Exhaling" if exhale else "Inhaling"
                bpm_text = "{}, BPM {:0.1f}, depth {:0.1f} mm".format(bstr, bpm, inhale_dist)
            else:
                bpm_text = None

            # Make an explicit copy, otherwise flip will not return a new object
            breath_hist_plot = self.breath_history[: self.hist_plot_len]
            breath_hist_plot = np.array(np.flip(breath_hist_plot, axis=0))
            breath_hist_plot -= (np.max(breath_hist_plot) + np.min(breath_hist_plot)) * 0.5

            zoom_hist_plot = self.pulse_history[: self.hist_plot_len // 2]
            zoom_hist_plot = np.array(np.flip(zoom_hist_plot, axis=0))
            zoom_hist_plot -= (max(zoom_hist_plot) + min(zoom_hist_plot)) * 0.5

            out_data = {
                "peak_hist": self.peak_history[:100],
                "peak_std_mm": 2.5 * np.std(np.unwrap(np.angle(self.peak_history))) / (2.0 * pi),
                "env_ampl": abs(self.lp_sweep),
                "env_delta": self.lp_phase_weights,
                "peak_idx": peak_idx,
                "breathing_history": breath_hist_plot,
                "breathing_text": bpm_text,
                "zoom_hist": zoom_hist_plot,
            }

        self.last_lp_sweep = self.lp_sweep
        self.sweep_index += 1
        return out_data

    def lp(self, new, state, alpha):
        return alpha * state + (1 - alpha) * new

    def push(self, val, arr):
        res = np.empty_like(arr)
        res[0] = val
        res[1:] = arr[:-1]
        arr[...] = res

    def find_peaks(self, env, width):
        n = len(env)
        peaks = np.zeros((0, 2))
        for idx in range(0, n, width):
            mi = np.argmax(env[idx : min(idx + width, n)]) + idx
            mi2 = np.argmax(env[max(mi - width, 0) : min(mi + width, n)])
            mi2 += max(mi - width, 0)
            if mi == mi2 and (0 < mi < n - 1):
                peaks = np.concatenate((peaks, np.array([[mi, env[mi]]])), axis=0)
        return peaks


class PGUpdater:
    def __init__(self, sensor_config, processing_config, session_info):
        assert sensor_config.update_rate is not None

        f = sensor_config.update_rate
        self.depths = et.utils.get_range_depths(sensor_config, session_info)
        self.hist_plot_len_s = processing_config.hist_plot_len
        self.hist_plot_len = int(round(self.hist_plot_len_s * f))
        self.move_xs = (np.arange(-self.hist_plot_len, 0) + 1) / f
        self.smooth_max = et.utils.SmoothMax(f, hysteresis=0.4, tau_decay=1.5)

    def setup(self, win):
        win.setWindowTitle("Acconeer breathing example")
        win.resize(800, 600)

        self.env_plot = win.addPlot(title="Amplitude of IQ data and change")
        self.env_plot.setMenuEnabled(False)
        self.env_plot.setMouseEnabled(x=False, y=False)
        self.env_plot.hideButtons()
        self.env_plot.addLegend()
        self.env_plot.showGrid(x=True, y=True)
        self.env_curve = self.env_plot.plot(
            pen=et.utils.pg_pen_cycler(0),
            name="Amplitude of IQ data",
        )
        self.delta_curve = self.env_plot.plot(
            pen=et.utils.pg_pen_cycler(1),
            name="Phase change between sweeps",
        )
        self.peak_vline = pg.InfiniteLine(pen=pg.mkPen("k", width=2.5, style=QtCore.Qt.DashLine))
        self.env_plot.addItem(self.peak_vline)

        self.peak_plot = win.addPlot(title="Phase of IQ at peak")
        self.peak_plot.setMenuEnabled(False)
        self.peak_plot.setMouseEnabled(x=False, y=False)
        self.peak_plot.hideButtons()
        et.utils.pg_setup_polar_plot(self.peak_plot, 1)
        self.peak_curve = self.peak_plot.plot(pen=et.utils.pg_pen_cycler(0))
        self.peak_scatter = pg.ScatterPlotItem(brush=pg.mkBrush("k"), size=15)
        self.peak_plot.addItem(self.peak_scatter)
        self.peak_text_item = pg.TextItem(color=pg.mkColor("k"), anchor=(0, 1))
        self.peak_plot.addItem(self.peak_text_item)
        self.peak_text_item.setPos(-1.15, -1.15)

        win.nextRow()

        self.zoom_plot = win.addPlot(title="Relative movement")
        self.zoom_plot.setMenuEnabled(False)
        self.zoom_plot.setMouseEnabled(x=False, y=False)
        self.zoom_plot.hideButtons()
        self.zoom_plot.showGrid(x=True, y=True)
        self.zoom_plot.setLabel("bottom", "Time (s)")
        self.zoom_plot.setLabel("left", "Movement (mm)")
        self.zoom_curve = self.zoom_plot.plot(pen=et.utils.pg_pen_cycler(0))

        self.move_plot = win.addPlot(title="Breathing movement")
        self.move_plot.setMenuEnabled(False)
        self.move_plot.setMouseEnabled(x=False, y=False)
        self.move_plot.hideButtons()
        self.move_plot.showGrid(x=True, y=True)
        self.move_plot.setLabel("bottom", "Time (s)")
        self.move_plot.setLabel("left", "Movement (mm)")
        self.move_plot.setYRange(-2, 2)
        self.move_plot.setXRange(-self.hist_plot_len_s, 0)
        self.move_curve = self.move_plot.plot(pen=et.utils.pg_pen_cycler(0))
        self.move_text_item = pg.TextItem(color=pg.mkColor("k"), anchor=(0, 1))
        self.move_text_item.setPos(self.move_xs[0], -2)
        self.move_plot.addItem(self.move_text_item)

    def update(self, data):
        envelope = data["env_ampl"]
        m = self.smooth_max.update(envelope)
        plot_delta = data["env_delta"] * m * 2e-5 + 0.5 * m

        norm_peak_hist_re = np.real(data["peak_hist"]) / m
        norm_peak_hist_im = np.imag(data["peak_hist"]) / m
        peak_std_text = "Std: {:.3f}mm".format(data["peak_std_mm"])
        peak_x = self.depths[data["peak_idx"]]

        self.env_plot.setYRange(0, m)
        self.env_curve.setData(self.depths, envelope)
        self.delta_curve.setData(self.depths, plot_delta)

        self.peak_scatter.setData([norm_peak_hist_re[0]], [norm_peak_hist_im[0]])
        self.peak_curve.setData(norm_peak_hist_re, norm_peak_hist_im)
        self.peak_text_item.setText(peak_std_text)
        self.peak_vline.setValue(peak_x)

        m = max(2, max(np.abs(data["breathing_history"])))

        self.move_curve.setData(self.move_xs, data["breathing_history"])
        self.move_plot.setYRange(-m, m)
        self.move_text_item.setPos(self.move_xs[0], -m)
        self.zoom_curve.setData(self.move_xs[self.move_xs.size // 2 :], data["zoom_hist"])
        self.move_text_item.setText(data["breathing_text"])


if __name__ == "__main__":
    main()
