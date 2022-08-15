# Copyright (c) Acconeer AB, 2022
# All rights reserved

import numpy as np

import acconeer.exptool as et


def main():
    args = et.a111.ExampleArgumentParser().parse_args()
    et.utils.config_logging(args)

    client = et.a111.Client(**et.a111.get_client_args(args))

    client.squeeze = False

    sensor_config = et.a111.IQServiceConfig()
    sensor_config.sensor = args.sensors
    sensor_config.range_interval = [0.2, 1.0]
    sensor_config.profile = sensor_config.Profile.PROFILE_2
    sensor_config.hw_accelerated_average_samples = 20
    sensor_config.downsampling_factor = 2

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
        win.setWindowTitle("Acconeer IQ example")

        self.ampl_plot = win.addPlot()
        self.ampl_plot.setMenuEnabled(False)
        self.ampl_plot.setMouseEnabled(x=False, y=False)
        self.ampl_plot.hideButtons()
        self.ampl_plot.showGrid(x=True, y=True)
        self.ampl_plot.setLabel("bottom", "Depth (m)")
        self.ampl_plot.setLabel("left", "Amplitude")
        win.nextRow()
        self.phase_plot = win.addPlot()
        self.phase_plot.setMenuEnabled(False)
        self.phase_plot.setMouseEnabled(x=False, y=False)
        self.phase_plot.hideButtons()
        self.phase_plot.showGrid(x=True, y=True)
        self.phase_plot.setLabel("bottom", "Depth (m)")
        self.phase_plot.setLabel("left", "Phase")
        self.phase_plot.setYRange(-np.pi, np.pi)
        self.phase_plot.getAxis("left").setTicks(et.utils.pg_phase_ticks)

        self.ampl_curves = []
        self.phase_curves = []
        for i, _ in enumerate(self.sensor_config.sensor):
            pen = et.utils.pg_pen_cycler(i)
            self.ampl_curves.append(self.ampl_plot.plot(pen=pen))
            self.phase_curves.append(self.phase_plot.plot(pen=pen))

        self.smooth_max = et.utils.SmoothMax(self.sensor_config.update_rate)

    def update(self, data):
        for ampl_curve, phase_curve, ys in zip(self.ampl_curves, self.phase_curves, data):
            ampl_curve.setData(self.depths, np.abs(ys))
            phase_curve.setData(self.depths, np.angle(ys))

        self.ampl_plot.setYRange(0, self.smooth_max.update(np.abs(data)))


if __name__ == "__main__":
    main()
