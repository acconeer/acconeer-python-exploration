import numpy as np
import pyqtgraph as pg

import acconeer.exptool as et


def main():
    args = et.utils.ExampleArgumentParser(num_sens=1).parse_args()
    et.utils.config_logging(args)

    if args.socket_addr:
        client = et.SocketClient(args.socket_addr)
    elif args.spi:
        client = et.SPIClient()
    else:
        port = args.serial_port or et.utils.autodetect_serial_port()
        client = et.UARTClient(port)

    sensor_config = get_sensor_config()
    processing_config = get_processing_config()
    sensor_config.sensor = args.sensors

    session_info = client.setup_session(sensor_config)

    pg_updater = PGUpdater(sensor_config, processing_config, session_info)
    pg_process = et.PGProcess(pg_updater)
    pg_process.start()

    client.start_session()

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    processor = Processor(sensor_config, processing_config, session_info)

    while not interrupt_handler.got_signal:
        info, data = client.get_next()
        plot_data = processor.process(data)

        if plot_data is not None:
            try:
                pg_process.put_data(plot_data)
            except et.PGProccessDiedException:
                break

    print("Disconnecting...")
    pg_process.close()
    client.disconnect()


def get_sensor_config():
    config = et.configs.SparseServiceConfig()
    config.profile = et.configs.SparseServiceConfig.Profile.PROFILE_3
    config.range_interval = [0.48, 0.72]
    config.sweeps_per_frame = 16
    config.hw_accelerated_average_samples = 60
    config.update_rate = 60
    return config


class ProcessingConfiguration(et.configbase.ProcessingConfig):
    VERSION = 1
    WINDOW_SIZE_POW_OF_2_MAX = 12
    ROLLING_HISTORY_SIZE_MAX = 1000

    show_time_domain = et.configbase.BoolParameter(
        label="Show data in time domain",
        default_value=True,
        updateable=True,
        order=0,
    )

    show_spect_history = et.configbase.BoolParameter(
        label="Show spectrum history",
        default_value=False,
        updateable=True,
        order=10,
    )

    show_depthwise_spect = et.configbase.BoolParameter(
        label="Show depthwise spectrum",
        default_value=False,
        updateable=True,
        order=20,
    )

    window_size_pow_of_2 = et.configbase.FloatParameter(
        label="Window size, power of 2",
        default_value=8,
        limits=(3, WINDOW_SIZE_POW_OF_2_MAX),
        decimals=0,
        updateable=True,
        order=100,
    )

    _window_size = et.configbase.get_virtual_parameter_class(et.configbase.IntParameter)(
        label="Window size",
        get_fun=lambda conf: 2 ** int(conf.window_size_pow_of_2),
        visible=False,
    )

    overlap = et.configbase.FloatParameter(
        label="Overlap",
        default_value=0.95,
        limits=(0, 1),
        updateable=True,
        order=200,
    )

    rolling_history_size = et.configbase.FloatParameter(
        label="Rolling history size",
        default_value=100,
        decimals=0,
        logscale=True,
        limits=(10, ROLLING_HISTORY_SIZE_MAX),
        updateable=True,
        order=300,
    )

    def check(self):
        alerts = super().check()

        msg = "{}".format(self._window_size)
        alerts.append(et.configbase.Info("window_size_pow_of_2", msg))

        return alerts


get_processing_config = ProcessingConfiguration


class Processor:
    def __init__(self, sensor_config, processing_config, session_info):
        self.f = sensor_config.update_rate
        depths = et.utils.get_range_depths(sensor_config, session_info)
        self.num_depths = depths.size

        max_window_size = 2 ** ProcessingConfiguration.WINDOW_SIZE_POW_OF_2_MAX
        self.sweep_history = np.full([max_window_size, self.num_depths], np.nan)

        self.collapsed_asd = None
        self.collapsed_asd_history = None

        self.window_size = None
        self.frames_between_updates = None
        self.rolling_history_size = None

        self.tick_idx = 0
        self.last_update_tick = 0

        self.update_processing_config(processing_config)

    def update_processing_config(self, processing_config):
        invalid = self.window_size != processing_config._window_size

        self.window_size = processing_config._window_size
        self.frames_between_updates = int(round(
            self.window_size * (1 - processing_config.overlap)))

        self.rolling_history_size = int(processing_config.rolling_history_size)

        if invalid:
            self.collapsed_asd_history = np.zeros([
                ProcessingConfiguration.ROLLING_HISTORY_SIZE_MAX,
                self.window_size // 2,
            ])

        if invalid and self.tick_idx > 0:
            self.update_spect()

    def process(self, frame):
        mean_sweep = frame.mean(axis=0)

        self.sweep_history = np.roll(self.sweep_history, -1, axis=0)
        self.sweep_history[-1] = mean_sweep

        outdated = (self.tick_idx - self.last_update_tick) > self.frames_between_updates
        if self.tick_idx == 0 or outdated:
            self.update_spect()

        self.tick_idx += 1

        return self.gather_result()

    def update_spect(self):
        x = self.sweep_history[-self.window_size :]
        x = x - np.nanmean(x, axis=0, keepdims=True)
        x = np.nan_to_num(x)
        fft = np.fft.rfft(x.T * np.hanning(x.shape[0]), axis=1)
        asd = np.abs(fft)[:, 1 :]

        self.collapsed_asd = asd.sum(axis=0)
        self.dw_asd = asd

        self.collapsed_asd_history = np.roll(self.collapsed_asd_history, -1, axis=0)
        self.collapsed_asd_history[-1] = self.collapsed_asd

        self.last_update_tick = self.tick_idx

    def gather_result(self):
        ts = np.arange(-self.window_size, 0, dtype="float") + 1
        fs = np.arange(self.window_size // 2, dtype="float") + 1

        if self.f:
            ts *= 1 / self.f
            fs *= 0.5 * self.f / fs[-1]

        cropped_history = self.collapsed_asd_history[-self.rolling_history_size :]

        return {
            "ts": ts,
            "sweep_history": self.sweep_history[-self.window_size :],
            "fs": fs,
            "collapsed_asd": self.collapsed_asd,
            "collapsed_asd_history": cropped_history,
            "dw_asd": self.dw_asd,
        }


class PGUpdater:
    def __init__(self, sensor_config, processing_config, session_info):
        self.processing_config = processing_config

        self.f = sensor_config.update_rate
        self.depths = et.utils.get_range_depths(sensor_config, session_info)
        self.downsampling_factor = sensor_config.downsampling_factor
        self.step_length = session_info["step_length_m"]

        self.td_smooth_lims = et.utils.SmoothLimits()
        self.collapsed_smooth_max = et.utils.SmoothMax(
            tau_grow=0.1,
        )

        self.setup_is_done = False

    def setup(self, win):
        self.td_plot = win.addPlot(row=0, col=0, title="PSD input data")
        self.td_plot.setMenuEnabled(False)
        self.td_plot.setMouseEnabled(x=False, y=False)
        self.td_plot.hideButtons()
        self.td_plot.addLegend()
        self.td_curves = []
        for i, depth in enumerate(self.depths):
            name = "{:.0f} cm".format(depth * 100)
            curve = self.td_plot.plot(pen=et.utils.pg_pen_cycler(i), name=name)
            self.td_curves.append(curve)

        self.collapsed_plot = win.addPlot(
            row=1, col=0, title="Collapsed sqrt(PSD)")
        self.collapsed_plot.setMenuEnabled(False)
        self.collapsed_plot.setMouseEnabled(x=False, y=False)
        self.collapsed_plot.hideButtons()
        self.collapsed_plot.setXRange(0, 1)
        self.collapsed_curve = self.collapsed_plot.plot(pen=et.utils.pg_pen_cycler())
        self.collapsed_vline = pg.InfiniteLine(pen=et.utils.pg_pen_cycler())
        self.collapsed_vline.hide()
        self.collapsed_plot.addItem(self.collapsed_vline)

        bg = pg.mkColor(0xFF, 0xFF, 0xFF, 150)
        self.collapsed_text = pg.TextItem(anchor=(0, 1), color="k", fill=bg)
        self.collapsed_text.setPos(0, 0)
        self.collapsed_text.setZValue(100)
        self.collapsed_plot.addItem(self.collapsed_text)

        self.collapsed_history_plot = win.addPlot(
            row=2, col=0, title="Collapsed sqrt(PSD) history")
        self.collapsed_history_plot.setMenuEnabled(False)
        self.collapsed_history_plot.setMouseEnabled(x=False, y=False)
        self.collapsed_history_plot.hideButtons()
        self.collapsed_history_im = pg.ImageItem()
        self.collapsed_history_im.setLookupTable(et.utils.pg_mpl_cmap("viridis"))
        self.collapsed_history_plot.addItem(self.collapsed_history_im)

        self.dw_plot = win.addPlot(row=3, col=0, title="Depthwise PSD")
        self.dw_plot.setMenuEnabled(False)
        self.dw_plot.setMouseEnabled(x=False, y=False)
        self.dw_plot.hideButtons()
        self.dw_im = pg.ImageItem()
        self.dw_im.setLookupTable(et.utils.pg_mpl_cmap("viridis"))
        self.dw_plot.addItem(self.dw_im)
        self.dw_plot.setLabel("bottom", "Depth (cm)")
        self.dw_plot.getAxis("bottom").setTickSpacing(6 * self.downsampling_factor, 6)

        self.setup_is_done = True
        self.update_processing_config()

    def update_processing_config(self, processing_config=None):
        if processing_config is None:
            processing_config = self.processing_config
        else:
            self.processing_config = processing_config

        if not self.setup_is_done:
            return

        self.td_plot.setVisible(processing_config.show_time_domain)
        self.collapsed_history_plot.setVisible(processing_config.show_spect_history)
        self.dw_plot.setVisible(processing_config.show_depthwise_spect)

        lbl = "Time (s)" if self.f else "Frame index"
        self.td_plot.setLabel("bottom", lbl)

        lbl = "Frequency (Hz)" if self.f else "Frequency bin"
        self.collapsed_plot.setLabel("bottom", lbl)

        for plot in [self.dw_plot, self.collapsed_history_plot]:
            plot.setLabel("left", lbl)

        if self.f:
            f_res = self.f / self.processing_config._window_size
        else:
            f_res = 1

        self.dw_im.resetTransform()
        self.dw_im.translate(100 * (self.depths[0] - self.step_length / 2), 0)
        self.dw_im.scale(100 * self.step_length, f_res)

        self.collapsed_history_im.resetTransform()
        self.collapsed_history_im.translate(0, f_res / 2)
        self.collapsed_history_im.scale(-1, f_res)

    def update(self, d):
        x = d["ts"]
        for i, curve in enumerate(self.td_curves):
            y = d["sweep_history"][:, i]
            et.utils.pg_curve_set_data_with_nan(curve, x, y)

        r = self.td_smooth_lims.update(d["sweep_history"])
        self.td_plot.setYRange(*r)

        x = d["fs"]
        y = d["collapsed_asd"]
        self.collapsed_curve.setData(x, y)
        m = self.collapsed_smooth_max.update(y)
        self.collapsed_plot.setXRange(0, x[-1])
        self.collapsed_plot.setYRange(0, m)

        f_max = x[y.argmax()]
        self.collapsed_vline.setPos(f_max)
        self.collapsed_vline.show()

        if self.f:
            s = "Peak: {:5.1f} Hz".format(f_max)
        else:
            s = "Peak: {:3.0f}".format(f_max)
        self.collapsed_text.setText(s)

        im = self.collapsed_history_im
        y = d["collapsed_asd_history"]
        im.updateImage(y[:: -1], levels=(0, 1.05 * y.max()))

        y = d["dw_asd"]
        m = max(1, np.max(y)) * 1.05
        self.dw_im.updateImage(y, levels=(0, m))


if __name__ == "__main__":
    main()
