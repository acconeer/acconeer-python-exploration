# Copyright (c) Acconeer AB, 2022
# All rights reserved

import numpy as np

from PySide6 import QtGui, QtWidgets

import pyqtgraph as pg

import acconeer.exptool as et


def main():
    args = et.a111.ExampleArgumentParser(num_sens=1).parse_args()
    et.utils.config_logging(args)

    client = et.a111.Client(**et.a111.get_client_args(args))

    config = et.a111.EnvelopeServiceConfig()
    config.sensor = args.sensors
    config.update_rate = 30

    session_info = client.setup_session(config)

    start = session_info["range_start_m"]
    length = session_info["range_length_m"]
    num_depths = session_info["data_length"]
    step_length = session_info["step_length_m"]
    depths = np.linspace(start, start + length, num_depths)
    num_hist = 2 * int(round(config.update_rate))
    hist_data = np.zeros([num_hist, depths.size])
    smooth_max = et.utils.SmoothMax(config.update_rate)

    app = QtWidgets.QApplication([])
    pg.setConfigOption("background", "w")
    pg.setConfigOption("foreground", "k")
    pg.setConfigOptions(antialias=True)
    win = pg.GraphicsLayoutWidget()
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
    tr = QtGui.QTransform()
    tr.translate(-2, start)
    tr.scale(2 / num_hist, step_length)
    hist_image_item.setTransform(tr)
    hist_plot.addItem(hist_image_item)

    # Get a nice colormap from matplotlib
    hist_image_item.setLookupTable(et.utils.pg_mpl_cmap("viridis"))

    win.show()

    interrupt_handler = et.utils.ExampleInterruptHandler()
    win.closeEvent = lambda _: interrupt_handler.force_signal_interrupt()
    print("Press Ctrl-C to end session")

    client.start_session()

    while not interrupt_handler.got_signal:
        info, data = client.get_next()

        hist_data = np.roll(hist_data, -1, axis=0)
        hist_data[-1] = data

        env_curve.setData(depths, data)
        env_plot.setYRange(0, smooth_max.update(data))
        hist_image_item.updateImage(hist_data, levels=(0, np.max(hist_data) * 1.05))

        app.processEvents()

    print("Disconnecting...")
    app.closeAllWindows()
    client.disconnect()


if __name__ == "__main__":
    main()
