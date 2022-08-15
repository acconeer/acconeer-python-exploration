# Copyright (c) Acconeer AB, 2022
# All rights reserved

import pyqtgraph as pg

import acconeer.exptool as et


def main():
    args = et.a111.ExampleArgumentParser().parse_args()
    et.utils.config_logging(args)

    client = et.a111.Client(**et.a111.get_client_args(args))

    client.squeeze = False

    sensor_config = et.a111.PowerBinServiceConfig()
    sensor_config.sensor = args.sensors
    sensor_config.range_interval = [0.1, 0.7]

    session_info = client.setup_session(sensor_config)

    pg_updater = PGUpdater(sensor_config, None, session_info)
    pg_process = et.PGProcess(pg_updater)
    pg_process.start()

    client.start_session()

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    while not interrupt_handler.got_signal:
        data_info, data = client.get_next()

        try:
            pg_process.put_data(data)
        except et.PGProccessDiedException:
            break

    print("Disconnecting...")
    pg_process.close()
    client.disconnect()


class PGUpdater:
    def __init__(self, sensor_config, processing_config, session_info):
        self.sensor_config = sensor_config
        self.depths = et.a111.get_range_depths(sensor_config, session_info)

    def setup(self, win):
        win.setWindowTitle("Acconeer power bins example")

        self.plot = win.addPlot()
        self.plot.setMenuEnabled(False)
        self.plot.setMouseEnabled(x=False, y=False)
        self.plot.hideButtons()
        self.plot.showGrid(x=True, y=True)
        self.plot.setLabel("bottom", "Depth (m)")
        self.plot.setLabel("left", "Amplitude")

        self.curves = []
        for i, _ in enumerate(self.sensor_config.sensor):
            curve = self.plot.plot(
                pen=et.utils.pg_pen_cycler(i),
                symbol="o",
                symbolPen="k",
                symbolBrush=pg.mkBrush(et.utils.color_cycler(i)),
            )
            self.curves.append(curve)

        self.smooth_max = et.utils.SmoothMax(self.sensor_config.update_rate)

    def update(self, data):
        for curve, ys in zip(self.curves, data):
            curve.setData(self.depths, ys)

        self.plot.setYRange(0, self.smooth_max.update(data))


if __name__ == "__main__":
    main()
