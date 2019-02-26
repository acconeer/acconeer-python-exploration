import numpy as np
from numpy import pi, unravel_index
from PyQt5 import QtCore
import pyqtgraph as pg
from scipy.fftpack import fft, fftshift

from acconeer_utils.clients.reg.client import RegClient
from acconeer_utils.clients.json.client import JSONClient
from acconeer_utils.clients import configs
from acconeer_utils import example_utils
from acconeer_utils.pg_process import PGProcess, PGProccessDiedException


fft_sweep_len = 17
rolling_sweeps = 4
threshold = 0.05        # Ignore data below threshold in fft window
max_speed = 8.00        # Max speed to be resolved with FFT in cm/s
wavelength = 0.49       # Wavelength of radar in cm


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

    processor = ObstacleDetectionProcessor(config)

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
    config.range_interval = [0.1, 0.5]
    config.sweep_rate = int(np.ceil(max_speed * 4 / wavelength))
    config.gain = 0.7
    return config


class ObstacleDetectionProcessor:
    def __init__(self, config):
        self.config = config
        self.sweep_index = 0

    def process(self, sweep):
        if self.sweep_index == 0:
            len_range = len(sweep)
            self.sweep_map = np.zeros((len_range, fft_sweep_len), dtype="complex")
            self.hamming_map = np.zeros((len_range, fft_sweep_len))
            for i in range(len_range):
                self.hamming_map[i, :] = np.hamming(fft_sweep_len)

        self.push(sweep, self.sweep_map)
        signalFFT = fftshift(fft(self.sweep_map*self.hamming_map, axis=1), axes=1)
        signalPSD = np.square(np.abs(signalFFT))
        env = np.abs(sweep)

        fft_peak, peak_avg = self.find_peaks(signalPSD)

        fft_max_env = env
        angle = None
        velocity = None
        peak_idx = np.argmax(env)

        if peak_avg is not None:
            fft_max_env = signalPSD[:, fft_peak[1]]
            zero = np.floor(fft_sweep_len / 2)
            angle_index = np.abs(peak_avg - zero)
            angle = np.arccos(angle_index / zero) / pi * 180
            velocity = (angle_index / zero) * wavelength * self.config.sweep_rate / 4
            peak_idx = fft_peak[0]

        out_data = {
            "env_ampl": env,
            "fft_max_env": fft_max_env,
            "fft_map": signalPSD,
            "peak_idx": peak_idx,
            "angle": angle,
            "velocity": velocity,
            "fft_peak": fft_peak,
            "fft_peak_avg": peak_avg,
        }

        self.sweep_index += 1
        return out_data

    def push(self, sweep, arr):
        res = np.empty_like(arr)
        res[:, 0] = sweep
        res[:, 1:] = arr[:, :-1]
        arr[...] = res

    def find_peaks(self, arr, dead_zone=2):
        peak = unravel_index(np.argmax(arr), arr.shape)
        peak_avg = peak[1]

        amp_sum = 0
        s = 0
        for i in range(3):
            if peak[1] - 1 + i < fft_sweep_len:
                s += arr[peak[0], (peak[1] - 1 + i)] * (peak[1] - 1 + i)
                amp_sum += arr[peak[0], (peak[1] - 1 + i)]
                peak_avg = s / amp_sum

        peak_avg = max(0, peak_avg)
        peak_avg = min(peak_avg, fft_sweep_len)

        if arr[peak[0], peak[1]] < threshold:
            peak = None
            peak_avg = None

        return peak, peak_avg


class PGUpdater:
    def __init__(self, config):
        self.config = config
        self.plot_index = 0
        self.map_max = 0
        self.width = 3
        self.max_velocity = wavelength/4*config.sweep_rate  # cm/s

    def setup(self, win):
        win.setWindowTitle("Acconeer obstacle detection example")

        self.env_ax = win.addPlot(row=0, col=0, title="Envelope and max FFT")
        self.env_ax.setLabel("bottom", "Depth (cm)")
        self.env_ax.setXRange(*(self.config.range_interval * 100))
        self.env_ax.showGrid(True, True)
        self.env_ax.addLegend()
        self.env_ax.setYRange(0, 0.1)

        self.env_ampl = self.env_ax.plot(pen=example_utils.pg_pen_cycler(0), name="Envelope")
        self.fft_max = self.env_ax.plot(pen=example_utils.pg_pen_cycler(1, "--"), name="FFT max")

        self.peak_dist_text = pg.TextItem(color="k", anchor=(0, 1))
        self.env_ax.addItem(self.peak_dist_text)
        self.peak_dist_text.setPos(self.config.range_start*100, 0)
        self.peak_dist_text.setZValue(3)

        self.env_peak_vline = pg.InfiniteLine(pos=0, angle=90, pen=pg.mkPen(width=2,
                                              style=QtCore.Qt.DotLine))
        self.env_ax.addItem(self.env_peak_vline)

        self.obstacle_ax = win.addPlot(row=1, col=0, title="Obstacle map")
        self.obstacle_im = pg.ImageItem()
        self.obstacle_ax.setLabel("bottom", "Velocity (cm/s)")
        self.obstacle_ax.setLabel("left", "Distance (cm)")
        self.obstacle_im.setLookupTable(example_utils.pg_mpl_cmap("viridis"))
        self.obstacle_ax.addItem(self.obstacle_im)

        self.obstacle_ax.setXRange(-self.max_velocity, self.max_velocity)
        self.obstacle_ax.setYRange(*self.config.range_interval * 100)

        self.obstacle_peak = pg.ScatterPlotItem(brush=pg.mkBrush("k"), size=15)
        self.obstacle_ax.addItem(self.obstacle_peak)

        self.peak_fft_text = pg.TextItem(color="w", anchor=(0, 1))
        self.obstacle_ax.addItem(self.peak_fft_text)
        self.peak_fft_text.setPos(-self.max_velocity, self.config.range_start*100)

        self.smooth_max = example_utils.SmoothMax(
                self.config.sweep_rate,
                tau_decay=1,
                tau_grow=0.2
                )

    def update(self, data):
        ds = 32  # downsampling
        if self.plot_index == 0:
            num_points = data["env_ampl"].size
            nfft = data["fft_map"].shape[1]

            self.env_xs = np.linspace(*self.config.range_interval*100, num_points)
            self.peak_x = self.env_xs[data["peak_idx"]]

            self.obstacle_im.translate(-self.max_velocity, self.config.range_start*100)
            self.obstacle_im.scale(
                    2*self.max_velocity/nfft,
                    self.config.range_length*100/num_points*ds
                    )
        else:
            self.peak_x = self.peak_x * 0.7 + 0.3 * self.env_xs[data["peak_idx"]]

        peak_dist_text = "Peak: {:.1f}mm".format(self.peak_x)
        peak_fft_text = "No peaks found"

        if data["fft_peak_avg"] is not None:
            dist = self.env_xs[data["fft_peak"][0]]
            vel = (data["fft_peak"][1] / data["fft_map"].shape[1] * 2 - 1) * self.max_velocity
            peak_fft_text = "Dist: {:.1f}cm, Speed/Angle: {:.1f}cm/s / {:.0f}".format(
                                dist, data["velocity"], data["angle"])

            half_pixel = self.max_velocity / np.floor(fft_sweep_len / 2) / 2
            self.obstacle_peak.setData([vel + half_pixel], [dist])
        else:
            self.obstacle_peak.setData([], [])

        self.peak_dist_text.setText(peak_dist_text)
        self.peak_fft_text.setText(peak_fft_text)

        self.env_ampl.setData(self.env_xs, data["env_ampl"])
        self.env_peak_vline.setValue(self.peak_x)

        env_max = np.max(data["env_ampl"])
        if data["fft_peak_avg"] is not None:
            fft_max = np.max(data["fft_max_env"])
            env_max = max(env_max, fft_max)

        self.env_ax.setYRange(0, self.smooth_max.update(env_max))

        self.fft_max.setData(self.env_xs, data["fft_max_env"])

        map_max = np.max(np.max(data["fft_map"]))
        fft_data = data["fft_map"].T

        g = 1/2.2
        fft_data = 254/map_max**g * fft_data**g

        fft_data[fft_data > 254] = 254

        map_min = 0
        map_max = 256

        self.obstacle_im.updateImage(fft_data[:, ::ds], levels=(map_min, map_max))
        self.plot_index += 1


if __name__ == "__main__":
    main()
