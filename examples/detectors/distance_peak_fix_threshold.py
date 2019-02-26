import sys
import numpy as np
import pyqtgraph as pg

from acconeer_utils.clients.reg.client import RegClient
from acconeer_utils.clients import configs
from acconeer_utils import example_utils
from acconeer_utils.pg_process import PGProcess, PGProccessDiedException


def main():
    args = example_utils.ExampleArgumentParser().parse_args()
    example_utils.config_logging(args)

    if args.socket_addr:
        print("Using detectors is only supported with the XM112 module")
        sys.exit()
    else:
        port = args.serial_port or example_utils.autodetect_serial_port()
        client = RegClient(port)

    config = configs.DistancePeakDetectorConfig()
    config.sensor = args.sensors
    config.range_interval = [0.1, 0.7]
    config.sweep_rate = 60
    config.gain = 0.5

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
    def __init__(self, config):
        self.config = config

    def setup(self, win):
        win.setWindowTitle("Acconeer distance peak example")
        self.plot = win.addPlot(title="Peaks")
        self.plot.showGrid(x=True, y=True)
        self.plot.setLabel("bottom", "Depth (m)")
        self.plot.setLabel("left", "Amplitude")
        self.plot.setXRange(*self.config.range_interval)

        self.scatter = pg.ScatterPlotItem(size=15)
        self.plot.addItem(self.scatter)

        self.smooth_max = example_utils.SmoothMax(
                self.config.sweep_rate,
                hysteresis=0.6,
                tau_decay=3,
                )

    def update(self, data):
        self.scatter.setData(data[:, 0], data[:, 1])

        m = np.amax(data[:, 1]) if data.size > 0 else 1
        self.plot.setYRange(0, self.smooth_max.update(m))


if __name__ == "__main__":
    main()
