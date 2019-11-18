import numpy as np
import pyqtgraph as pg

from acconeer.exptool.clients import SocketClient, SPIClient, UARTClient
from acconeer.exptool import configs
from acconeer.exptool import example_utils
from acconeer.exptool.pg_process import PGProcess, PGProccessDiedException


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

    config = configs.PowerBinServiceConfig()
    config.sensor = args.sensors
    config.range_interval = [0.1, 0.7]
    config.sweep_rate = 60
    config.gain = 0.6
    # config.bin_count = 8

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

        self.sweep_index = 0

    def setup(self, win):
        win.setWindowTitle("Acconeer power bins example")

        self.plot = win.addPlot(title="Power bins")
        self.plot.showGrid(x=True, y=True)
        self.plot.setLabel("bottom", "Depth (m)")
        self.plot.setLabel("left", "Amplitude")

        self.curves = []
        for i in range(len(self.config.sensor)):
            pen = example_utils.pg_pen_cycler(i)
            curve = self.plot.plot(
                    pen=pen,
                    symbol="o",
                    symbolPen="k",
                    symbolBrush=pg.mkBrush(example_utils.color_cycler(i))
                    )
            self.curves.append(curve)

        self.smooth_max = example_utils.SmoothMax(self.config.sweep_rate)

    def update(self, data):
        if self.sweep_index == 0:
            num_points = data.shape[1]
            self.xs = np.linspace(*self.config.range_interval, num_points)

        for i in range(data.shape[0]):
            self.curves[i].setData(self.xs, data[i])

        self.plot.setYRange(0, self.smooth_max.update(np.amax(data)))

        self.sweep_index += 1


if __name__ == "__main__":
    main()
