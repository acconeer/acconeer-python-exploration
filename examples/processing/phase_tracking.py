import numpy as np
import pyqtgraph as pg

from PyQt5 import QtCore

from acconeer.exptool import configs, utils
from acconeer.exptool.clients import SocketClient, SPIClient, UARTClient
from acconeer.exptool.pg_process import PGProccessDiedException, PGProcess


def main():
    args = utils.ExampleArgumentParser(num_sens=1).parse_args()
    utils.config_logging(args)

    if args.socket_addr:
        client = SocketClient(args.socket_addr)
    elif args.spi:
        client = SPIClient()
    else:
        port = args.serial_port or utils.autodetect_serial_port()
        client = UARTClient(port)

    sensor_config = get_sensor_config()
    sensor_config.sensor = args.sensors

    processing_config = None

    session_info = client.setup_session(sensor_config)

    pg_updater = PGUpdater(sensor_config, processing_config, session_info)
    pg_process = PGProcess(pg_updater)
    pg_process.start()

    client.start_session()

    interrupt_handler = utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    processor = PhaseTrackingProcessor(sensor_config, processing_config, session_info)

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


def get_sensor_config():
    config = configs.IQServiceConfig()
    config.range_interval = [0.3, 0.6]
    config.update_rate = 80
    config.repetition_mode = configs.IQServiceConfig.RepetitionMode.SENSOR_DRIVEN
    return config


class PhaseTrackingProcessor:
    def __init__(self, sensor_config, processing_config, session_info):
        assert sensor_config.update_rate is not None

        self.f = sensor_config.update_rate
        self.dt = 1 / self.f

        num_hist_points = int(round(self.f * 3))

        self.lp_vel = 0
        self.last_sweep = None
        self.hist_pos = np.zeros(num_hist_points)
        self.sweep_index = 0

    def process(self, sweep):
        n = len(sweep)

        ampl = np.abs(sweep)
        power = np.square(ampl)
        if np.sum(power) > 1e-6:
            com = np.sum(np.arange(n) / n * power) / np.sum(power)  # center of mass
        else:
            com = 0

        if self.sweep_index == 0:
            self.lp_ampl = ampl
            self.lp_com = com
            plot_data = None
        else:
            a = self.alpha(0.1, self.dt)
            self.lp_ampl = a * ampl + (1 - a) * self.lp_ampl
            a = self.alpha(0.25, self.dt)
            self.lp_com = a * com + (1 - a) * self.lp_com

            com_idx = int(self.lp_com * n)
            delta_angle = np.angle(sweep[com_idx] * np.conj(self.last_sweep[com_idx]))
            vel = self.f * 2.5 * delta_angle / (2 * np.pi)

            a = self.alpha(0.1, self.dt)
            self.lp_vel = a * vel + (1 - a) * self.lp_vel

            dp = self.lp_vel / self.f
            self.hist_pos = np.roll(self.hist_pos, -1)
            self.hist_pos[-1] = self.hist_pos[-2] + dp

            hist_len = len(self.hist_pos)
            plot_hist_pos = self.hist_pos - self.hist_pos.mean()
            cut_hist_pos = self.hist_pos[hist_len // 2 :]
            plot_hist_pos_zoom = cut_hist_pos - cut_hist_pos.mean()

            iq_val = np.exp(1j * np.angle(sweep[com_idx])) * self.lp_ampl[com_idx]

            plot_data = {
                "abs": self.lp_ampl,
                "arg": np.angle(sweep),
                "com": self.lp_com,
                "hist_pos": plot_hist_pos,
                "hist_pos_zoom": plot_hist_pos_zoom,
                "iq_val": iq_val,
            }

        self.last_sweep = sweep
        self.sweep_index += 1
        return plot_data

    def alpha(self, tau, dt):
        return 1 - np.exp(-dt / tau)


class PGUpdater:
    def __init__(self, sensor_config, processing_config, session_info):
        self.depths = utils.get_range_depths(sensor_config, session_info)
        self.smooth_max = utils.SmoothMax(sensor_config.update_rate)

    def setup(self, win):
        win.resize(800, 600)
        win.setWindowTitle("Acconeer phase tracking example")

        self.abs_plot = win.addPlot(row=0, col=0)
        self.abs_plot.setMenuEnabled(False)
        self.abs_plot.showGrid(x=True, y=True)
        self.abs_plot.setLabel("left", "Amplitude")
        self.abs_plot.setLabel("bottom", "Depth (m)")
        self.abs_curve = self.abs_plot.plot(pen=utils.pg_pen_cycler(0))
        pen = utils.pg_pen_cycler(1)
        pen.setStyle(QtCore.Qt.DashLine)
        self.abs_inf_line = pg.InfiniteLine(pen=pen)
        self.abs_plot.addItem(self.abs_inf_line)

        self.arg_plot = win.addPlot(row=1, col=0)
        self.arg_plot.setMenuEnabled(False)
        self.arg_plot.showGrid(x=True, y=True)
        self.arg_plot.setLabel("bottom", "Depth (m)")
        self.arg_plot.setLabel("left", "Phase")
        self.arg_plot.setYRange(-np.pi, np.pi)
        self.arg_plot.getAxis("left").setTicks(utils.pg_phase_ticks)
        self.arg_curve = self.arg_plot.plot(pen=utils.pg_pen_cycler())
        self.arg_inf_line = pg.InfiniteLine(pen=pen)
        self.arg_plot.addItem(self.arg_inf_line)

        self.iq_plot = win.addPlot(row=1, col=1, title="IQ at line")
        self.iq_plot.setMenuEnabled(False)
        utils.pg_setup_polar_plot(self.iq_plot, 1)
        self.iq_curve = self.iq_plot.plot(pen=utils.pg_pen_cycler())
        self.iq_scatter = pg.ScatterPlotItem(brush=pg.mkBrush(utils.color_cycler()), size=15)
        self.iq_plot.addItem(self.iq_scatter)

        self.hist_plot = win.addPlot(row=0, col=1, colspan=2)
        self.hist_plot.setMenuEnabled(False)
        self.hist_plot.showGrid(x=True, y=True)
        self.hist_plot.setLabel("bottom", "Time (s)")
        self.hist_plot.setLabel("left", "Tracking (mm)")
        self.hist_curve = self.hist_plot.plot(pen=utils.pg_pen_cycler())
        self.hist_plot.setYRange(-5, 5)

        self.hist_zoom_plot = win.addPlot(row=1, col=2)
        self.hist_zoom_plot.setMenuEnabled(False)
        self.hist_zoom_plot.showGrid(x=True, y=True)
        self.hist_zoom_plot.setLabel("bottom", "Time (s)")
        self.hist_zoom_plot.setLabel("left", "Tracking (mm)")
        self.hist_zoom_curve = self.hist_zoom_plot.plot(pen=utils.pg_pen_cycler())
        self.hist_zoom_plot.setYRange(-0.5, 0.5)

        self.first = True

    def update(self, data):
        if self.first:
            self.ts = np.linspace(-3, 0, len(data["hist_pos"]))
            self.ts_zoom = np.linspace(-1.5, 0, len(data["hist_pos_zoom"]))
            self.first = False

        com_x = (1 - data["com"]) * self.depths[0] + data["com"] * self.depths[-1]
        m = self.smooth_max.update(data["abs"])

        self.abs_curve.setData(self.depths, data["abs"])
        self.abs_plot.setYRange(0, m)
        self.abs_inf_line.setValue(com_x)
        self.arg_curve.setData(self.depths, data["arg"])
        self.arg_inf_line.setValue(com_x)
        self.hist_curve.setData(self.ts, data["hist_pos"])
        self.hist_zoom_curve.setData(self.ts_zoom, data["hist_pos_zoom"])

        norm_iq_val = data["iq_val"] / m
        self.iq_curve.setData([0, np.real(norm_iq_val)], [0, np.imag(norm_iq_val)])
        self.iq_scatter.setData([np.real(norm_iq_val)], [np.imag(norm_iq_val)])


if __name__ == "__main__":
    main()
