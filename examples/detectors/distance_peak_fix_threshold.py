import sys
import numpy as np
import pyqtgraph as pg
from PyQt5 import QtGui

from acconeer_utils.clients.reg.client import RegClient
from acconeer_utils.clients import configs
from acconeer_utils import example_utils


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
    config.gain = 0.55

    client.setup_session(config)

    # Setup PyQtGraph
    app = QtGui.QApplication([])
    pg.setConfigOption("background", "w")
    pg.setConfigOption("foreground", "k")
    pg.setConfigOptions(antialias=True)
    win = pg.GraphicsLayoutWidget()
    win.closeEvent = lambda _: interrupt_handler.force_signal_interrupt()
    win.setWindowTitle("Acconeer distance peak example")
    plot_updater = PGUpdater(win, config)
    win.show()
    app.processEvents()

    client.start_streaming()

    interrupt_handler = example_utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    while not interrupt_handler.got_signal:
        info, data = client.get_next()

        plot_updater.update(data)
        app.processEvents()

    print("Disconnecting...")
    app.closeAllWindows()
    client.disconnect()


class PGUpdater:
    def __init__(self, win, config):
        self.plot = win.addPlot(title="Peaks")
        self.plot.showGrid(x=True, y=True)
        self.plot.setLabel("bottom", "Depth (m)")
        self.plot.setLabel("left", "Amplitude")
        self.plot.setXRange(*config.range_interval)

        self.scatter = pg.ScatterPlotItem(size=15)
        self.plot.addItem(self.scatter)

        self.smooth_max = example_utils.SmoothMax(
                config.sweep_rate,
                hysteresis=0.6,
                tau_decay=3,
                )

    def update(self, data):
        self.scatter.setData(data[:, 0], data[:, 1])

        m = np.amax(data[:, 1]) if data.size > 0 else 1
        self.plot.setYRange(0, self.smooth_max.update(m))


if __name__ == "__main__":
    main()
