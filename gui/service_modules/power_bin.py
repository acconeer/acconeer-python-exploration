import numpy as np
import pyqtgraph as pg

from acconeer_utils.clients.reg.client import RegClient, RegSPIClient
from acconeer_utils.clients.json.client import JSONClient
from acconeer_utils.clients import configs
from acconeer_utils import example_utils
from acconeer_utils.pg_process import PGProcess, PGProccessDiedException


def main():
    args = example_utils.ExampleArgumentParser(num_sens=1).parse_args()
    example_utils.config_logging(args)

    if args.socket_addr:
        client = JSONClient(args.socket_addr)
    elif args.spi:
        client = RegSPIClient()
    else:
        port = args.serial_port or example_utils.autodetect_serial_port()
        client = RegClient(port)

    sensor_config = get_sensor_config()
    sensor_config.sensor = args.sensors

    client.setup_session(sensor_config)

    pg_updater = PGUpdater(sensor_config)
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


def get_sensor_config():
    return configs.PowerBinServiceConfig()


class PGUpdater:
    def __init__(self, sensor_config, processing_config=None):
        self.sensor_config = sensor_config

        self.sweep_index = 0

    def setup(self, win):
        win.setWindowTitle("Acconeer power bin example")

        self.plot = win.addPlot(title="Power bin")
        self.plot.showGrid(x=True, y=True)
        self.plot.setLabel("bottom", "Depth (m)")
        self.plot.setLabel("left", "Amplitude")
        self.plot.setYRange(0, 1)

        self.bar_graph = pg.BarGraphItem(
            x=[],
            height=[],
            width=0,
            brush=pg.mkBrush(example_utils.color_cycler()),
        )

        self.plot.addItem(self.bar_graph)

        self.smooth_max = example_utils.SmoothMax(self.sensor_config.sweep_rate)

    def update(self, data):
        if self.sweep_index == 0:
            num_points = data.size
            self.xs = np.linspace(*self.sensor_config.range_interval, num_points * 2 + 1)[1::2]
            bin_width = 0.8 * (self.sensor_config.range_length / num_points)
            self.plot.setXRange(*self.sensor_config.range_interval)
            self.bar_graph.setOpts(x=self.xs, width=bin_width)

        self.bar_graph.setOpts(height=data)
        self.plot.setYRange(0, self.smooth_max.update(np.max(data)))

        self.sweep_index += 1


if __name__ == "__main__":
    main()
