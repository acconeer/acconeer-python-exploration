import numpy as np
from numpy import square, exp
import pyqtgraph as pg
from PyQt5 import QtCore

from acconeer_utils.clients.reg.client import RegClient
from acconeer_utils.clients.json.client import JSONClient
from acconeer_utils.clients import configs
from acconeer_utils import example_utils
from acconeer_utils.pg_process import PGProcess, PGProccessDiedException


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

    processor = PresenceDetectionProcessor(config)

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
    config = configs.EnvelopeServiceConfig()
    config.session_profile = configs.EnvelopeServiceConfig.MAX_SNR
    config.range_interval = [0.3, 0.8]
    config.sweep_rate = 50
    config.gain = 0.7
    return config


class PresenceDetectionProcessor:
    def __init__(self, config):
        self.Ns = 10  # Number of sweeps per burst
        self.fb = config.sweep_rate//self.Ns
        self.t_fast = 0.2  # seconds
        self.t_slow = 2  # seconds
        self.t_move = 1  # seconds
        self.a_fast = exp(-2 / (self.fb*self.t_fast))
        self.a_slow = exp(-2 / (self.fb*self.t_slow))
        self.a_move = exp(-2 / (self.fb*self.t_move))
        self.p_fast = 0  # Power filtered with the fast filter parameter
        self.p_slow = 0  # Power filtered with the slow filter parameter
        self.p_slow_vec = np.ones((self.t_slow * config.sweep_rate)//(self.Ns))
        self.movement_history = np.zeros(5 * config.sweep_rate//self.Ns)  # 5 seconds
        self.movement_lp = 0

        self.sweep_index = 0

    def process(self, sweep):
        out_data = None

        if self.sweep_index == 0:
            self.sweep_burst_average = np.array(sweep)
            self.Nd = sweep.size
            self.sweep_burst_matrix = np.zeros([self.Nd, self.Ns])
        else:
            self.sweep_burst_matrix = np.roll(self.sweep_burst_matrix, -1, axis=1)
            self.sweep_burst_matrix[:, -1] = sweep

            if np.mod(self.sweep_index, self.Ns) == 0:  # Enters each burst
                # Average sweeps in burst
                self.sweep_burst_average = np.mean(square(abs(self.sweep_burst_matrix)), axis=1)

                p = sum(self.sweep_burst_average)
                self.p_fast = self.p_fast*self.a_fast + p*(1-self.a_fast)

                tmp = self.p_slow_vec[-1]
                self.p_slow_vec = np.roll(self.p_slow_vec, -1)

                # Update p_slow after calc motion
                self.p_slow_vec[-1] = tmp*self.a_slow + p*(1-self.a_slow)

                # Non-coherent motion metric
                movement = abs(self.p_fast-self.p_slow_vec[-1]) / self.p_slow_vec[-1]

                self.movement_lp = self.movement_lp*self.a_move + movement*(1-self.a_move)
                self.movement_history = np.roll(self.movement_history, -1)
                self.movement_history[-1] = self.movement_lp

                out_data = {
                    "envelope": abs(self.sweep_burst_average),
                    "movement_history": (self.movement_history),
                }

        self.sweep_index += 1
        return out_data


class PGUpdater:
    def __init__(self, config):
        self.config = config
        self.threshold = 0.4

    def setup(self, win):
        win.setWindowTitle("Acconeer presence detection example")

        self.env_plot = win.addPlot(title="Burst mean of Envelope²")
        self.env_plot.showGrid(x=True, y=True)
        self.env_plot.setLabel("bottom", "Depth (m)")
        self.env_curve = self.env_plot.plot(pen=example_utils.pg_pen_cycler(0))
        self.env_smooth_max = example_utils.SmoothMax(self.config.sweep_rate / 10)

        win.nextRow()
        move_hist_plot = win.addPlot(title="Changes in received power")
        move_hist_plot.showGrid(x=True, y=True)
        move_hist_plot.setLabel("bottom", "Time(s)")
        move_hist_plot.setXRange(-5, 0)
        move_hist_plot.setYRange(0, 1)
        self.move_hist_curve = move_hist_plot.plot(pen=example_utils.pg_pen_cycler(0))
        self.move_hist_smooth_max = example_utils.SmoothMax(self.config.sweep_rate / 10)
        limit_pen = pg.mkPen("k", width=2.5, style=QtCore.Qt.DashLine)
        limit_line = pg.InfiniteLine(self.threshold, angle=0, pen=limit_pen)
        move_hist_plot.addItem(limit_line)
        self.move_hist_text = pg.TextItem(color=pg.mkColor("k"), anchor=(0.5, 0))
        self.move_hist_text.setPos(-2.5, 0.95)
        move_hist_plot.addItem(self.move_hist_text)

    def update(self, data):
        env_ys = data["envelope"]
        env_xs = np.linspace(*self.config.range_interval, len(env_ys))
        self.env_curve.setData(env_xs, env_ys)
        self.env_plot.setYRange(0, self.env_smooth_max.update(np.amax(env_ys)))

        move_hist_ys = data["movement_history"]
        move_hist_xs = np.linspace(-5, 0, len(move_hist_ys))
        self.move_hist_curve.setData(move_hist_xs, move_hist_ys)

        if move_hist_ys[-1] > self.threshold:
            self.move_hist_text.setText("Present!")
        else:
            self.move_hist_text.setText("Not present")


if __name__ == "__main__":
    main()
