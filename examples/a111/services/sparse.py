# Copyright (c) Acconeer AB, 2022
# All rights reserved

import numpy as np

import pyqtgraph as pg

import acconeer.exptool as et


def main():
    args = et.a111.ExampleArgumentParser().parse_args()
    et.utils.config_logging(args)

    client = et.a111.Client(**et.a111.get_client_args(args))

    client.squeeze = False

    sensor_config = et.a111.SparseServiceConfig()
    sensor_config.sensor = args.sensors
    sensor_config.range_interval = [0.24, 1.20]
    sensor_config.sweeps_per_frame = 16
    sensor_config.hw_accelerated_average_samples = 60
    sensor_config.sampling_mode = sensor_config.SamplingMode.A
    sensor_config.profile = sensor_config.Profile.PROFILE_3
    sensor_config.gain = 0.6

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
        win.setWindowTitle("Acconeer sparse example")

        self.plots = []
        self.scatters = []
        self.smooth_lims = []
        for sensor_id in self.sensor_config.sensor:
            if len(self.sensor_config.sensor) > 1:
                plot = win.addPlot(title="Sensor {}".format(sensor_id))
            else:
                plot = win.addPlot()
            plot.setMenuEnabled(False)
            plot.setMouseEnabled(x=False, y=False)
            plot.hideButtons()
            plot.showGrid(x=True, y=True)
            plot.setLabel("bottom", "Depth (m)")
            plot.setLabel("left", "Amplitude")
            plot.setYRange(-(2**15), 2**15)
            scatter = pg.ScatterPlotItem(size=10)
            plot.addItem(scatter)
            win.nextRow()

            self.plots.append(plot)
            self.scatters.append(scatter)
            self.smooth_lims.append(et.utils.SmoothLimits(self.sensor_config.update_rate))

    def update(self, data):
        xs = np.tile(self.depths, self.sensor_config.sweeps_per_frame)

        for i, _ in enumerate(self.sensor_config.sensor):
            ys = data[i].flatten()
            self.scatters[i].setData(xs, ys)
            lims = self.smooth_lims[i].update(ys)
            self.plots[i].setYRange(*lims)


if __name__ == "__main__":
    main()
