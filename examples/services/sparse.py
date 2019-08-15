import numpy as np
import pyqtgraph as pg

from acconeer_utils.clients import SocketClient, SPIClient, UARTClient
from acconeer_utils.clients import configs
from acconeer_utils import example_utils
from acconeer_utils.pg_process import PGProcess, PGProccessDiedException


def main():
    args = example_utils.ExampleArgumentParser().parse_args()
    example_utils.config_logging(args)

    if args.socket_addr:
        client = SocketClient(args.socket_addr)
    elif args.spi:
        client = SPIClient()
    else:
        port = args.serial_port or example_utils.autodetect_serial_port()
        client = UARTClient(port)

    client.squeeze = False

    config = configs.SparseServiceConfig()
    config.sensor = args.sensors
    config.range_interval = [0.24, 1.20]
    config.sweep_rate = 60
    config.number_of_subsweeps = 16
    # config.hw_accelerated_average_samples = 60
    # config.stepsize = 1

    client.setup_session(config)

    pg_updater = PGUpdater(config)
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
    def __init__(self, sensor_config, processing_config=None):
        self.config = sensor_config

    def setup(self, win):
        win.setWindowTitle("Acconeer sparse example")

        self.plots = []
        self.scatters = []
        self.smooth_maxs = []
        for sensor_id in self.config.sensor:
            if len(self.config.sensor) > 1:
                plot = win.addPlot(title="Sensor {}".format(sensor_id))
            else:
                plot = win.addPlot()
            plot.showGrid(x=True, y=True)
            plot.setLabel("bottom", "Depth (m)")
            plot.setLabel("left", "Amplitude")
            plot.setYRange(-2**15, 2**15)
            scatter = pg.ScatterPlotItem(size=10)
            plot.addItem(scatter)
            win.nextRow()

            self.plots.append(plot)
            self.scatters.append(scatter)
            self.smooth_maxs.append(example_utils.SmoothMax(self.config.sweep_rate))

    def update(self, data):
        num_sensors, num_subsweeps, num_depths = data.shape
        xs = np.tile(np.linspace(*self.config.range_interval, num_depths), num_subsweeps)

        for i in range(num_sensors):
            ys = data[i].flatten()
            self.scatters[i].setData(xs, ys)
            m = self.smooth_maxs[i].update(max(2500, np.amax(np.abs(ys))))
            self.plots[i].setYRange(-m, m)


if __name__ == "__main__":
    main()
