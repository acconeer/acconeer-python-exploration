import numpy as np
from pyqtgraph.Qt import QtGui
import pyqtgraph as pg

from acconeer_utils.clients.reg.client import RegClient
from acconeer_utils.clients.json.client import JSONClient
from acconeer_utils.clients import configs
from acconeer_utils import example_utils


def main():
    args = example_utils.ExampleArgumentParser(num_sens=1).parse_args()
    example_utils.config_logging(args)

    if args.socket_addr:
        client = JSONClient(args.socket_addr)
    else:
        port = args.serial_port or example_utils.autodetect_serial_port()
        client = RegClient(port)

    config = configs.EnvelopeServiceConfig()
    config.sensor = args.sensors
    config.range_interval = [0.2, 0.6]
    config.sweep_rate = 60
    config.gain = 0.65

    info = client.setup_session(config)
    num_points = info["data_length"]
    xs = np.linspace(*config.range_interval, num_points)
    num_hist = 2*config.sweep_rate

    hist_data = np.zeros([num_hist, num_points])
    hist_max = np.zeros(num_hist)
    smooth_max = example_utils.SmoothMax(config.sweep_rate)

    app = QtGui.QApplication([])
    pg.setConfigOption("background", "w")
    pg.setConfigOption("foreground", "k")
    pg.setConfigOptions(antialias=True)
    win = pg.GraphicsLayoutWidget()
    win.closeEvent = lambda _: interrupt_handler.force_signal_interrupt()
    win.setWindowTitle("Acconeer PyQtGraph example")

    env_plot = win.addPlot(title="Envelope")
    env_plot.showGrid(x=True, y=True)
    env_plot.setLabel("bottom", "Depth (m)")
    env_plot.setLabel("left", "Amplitude")
    env_curve = env_plot.plot(pen=pg.mkPen("k", width=2))

    win.nextRow()
    hist_plot = win.addPlot()
    hist_plot.setLabel("bottom", "Time (s)")
    hist_plot.setLabel("left", "Depth (m)")
    hist_image_item = pg.ImageItem()
    hist_image_item.translate(-2, config.range_start)
    hist_image_item.scale(2/num_hist, config.range_length/num_points)
    hist_plot.addItem(hist_image_item)

    # try to get a colormap from matplotlib
    try:
        hist_image_item.setLookupTable(example_utils.pg_mpl_cmap("viridis"))
    except ImportError:
        pass

    win.show()

    interrupt_handler = example_utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    client.start_streaming()

    while not interrupt_handler.got_signal:
        info, sweep = client.get_next()

        hist_data = np.roll(hist_data, -1, axis=0)
        hist_data[-1] = sweep
        hist_max = np.roll(hist_max, -1)
        hist_max[-1] = np.max(sweep)
        y_max = smooth_max.update(np.amax(hist_max))
        env_curve.setData(xs, sweep)
        env_plot.setYRange(0, y_max)
        hist_image_item.updateImage(hist_data, levels=(0, y_max))

        app.processEvents()

    print("Disconnecting...")
    app.closeAllWindows()
    client.disconnect()


if __name__ == "__main__":
    main()
