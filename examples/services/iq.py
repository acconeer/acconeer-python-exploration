import numpy as np

from acconeer_utils.clients.reg.client import RegClient
from acconeer_utils.clients.json.client import JSONClient
from acconeer_utils.clients import configs
from acconeer_utils import example_utils
from acconeer_utils.pg_process import PGProcess, PGProccessDiedException


def main():
    args = example_utils.ExampleArgumentParser().parse_args()
    example_utils.config_logging(args)

    if args.socket_addr:
        client = JSONClient(args.socket_addr)
    else:
        port = args.serial_port or example_utils.autodetect_serial_port()
        client = RegClient(port)

    client.squeeze = False

    config = configs.IQServiceConfig()
    config.sensor = args.sensors
    config.range_interval = [0.2, 0.6]
    config.sweep_rate = 30
    config.gain = 0.6
    # config.running_average_factor = 0.5

    info = client.setup_session(config)
    num_points = info["data_length"]

    pg_updater = PGUpdater(config, num_points)
    pg_process = PGProcess(pg_updater)
    pg_process.start()

    client.start_streaming()

    interrupt_handler = example_utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    while not interrupt_handler.got_signal:
        info, data = client.get_next()

        try:
            pg_process.put_data(data)
        except PGProccessDiedException:
            break

    print("Disconnecting...")
    pg_process.close()
    client.disconnect()


class PGUpdater:
    def __init__(self, config, num_points):
        self.config = config
        self.num_points = num_points

    def setup(self, win):
        win.setWindowTitle("Acconeer IQ example")

        self.ampl_plot = win.addPlot(title="IQ")
        self.ampl_plot.showGrid(x=True, y=True)
        self.ampl_plot.setLabel("bottom", "Depth (m)")
        self.ampl_plot.setLabel("left", "Amplitude")
        win.nextRow()
        self.phase_plot = win.addPlot()
        self.phase_plot.showGrid(x=True, y=True)
        self.phase_plot.setLabel("bottom", "Depth (m)")
        self.phase_plot.setLabel("left", "Phase")
        self.phase_plot.setYRange(-np.pi, np.pi)
        self.phase_plot.getAxis("left").setTicks(example_utils.pg_phase_ticks)

        self.ampl_curves = []
        self.phase_curves = []
        for i in range(len(self.config.sensor)):
            pen = example_utils.pg_pen_cycler(i)
            self.ampl_curves.append(self.ampl_plot.plot(pen=pen))
            self.phase_curves.append(self.phase_plot.plot(pen=pen))

        self.xs = np.linspace(*self.config.range_interval, self.num_points)
        self.smooth_max = example_utils.SmoothMax(self.config.sweep_rate)

    def update(self, data):
        for i in range(data.shape[0]):
            self.ampl_curves[i].setData(self.xs, np.abs(data[i]))
            self.phase_curves[i].setData(self.xs, np.angle(data[i]))

        self.ampl_plot.setYRange(0, self.smooth_max.update(np.amax(np.abs(data))))


if __name__ == "__main__":
    main()
