import numpy as np
import pyqtgraph as pg

from acconeer.exptool.clients import SocketClient, SPIClient, UARTClient
from acconeer.exptool import configs
from acconeer.exptool import utils
from acconeer.exptool.pg_process import PGProcess, PGProccessDiedException
from acconeer.exptool.structs import configbase


def main():
    args = utils.ExampleArgumentParser(num_sens=1).parse_args()
    utils.config_logging(args)

    if args.socket_addr:
        client = SocketClient(args.socket_addr)
    elif args.spi:
        client = SPIClient()
    else:
        port = args.serial_port or utils.autodetect_serial_port()
        client = UARTClient(port)

    sensor_config = get_sensor_config()
    processing_config = get_processing_config()
    sensor_config.sensor = args.sensors

    session_info = client.setup_session(sensor_config)

    pg_updater = PGUpdater(sensor_config, processing_config, session_info)
    pg_process = PGProcess(pg_updater)
    pg_process.start()

    client.start_session()

    interrupt_handler = utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    processor = Processor(sensor_config, processing_config, session_info)

    while not interrupt_handler.got_signal:
        info, sweep = client.get_next()
        plot_data = processor.process(sweep)

        if plot_data is not None:
            try:
                pg_process.put_data(plot_data)
            except PGProccessDiedException:
                break

    print("Disconnecting...")
    pg_process.close()
    client.disconnect()


def get_sensor_config():
    config = configs.SparseServiceConfig()
    config.range_interval = [0.24, 0.48]
    config.sampling_mode = config.SAMPLING_MODE_A
    config.number_of_subsweeps = 64
    config.subsweep_rate = 3e3

    # max frequency
    config.sweep_rate = 100
    config.experimental_stitching = True

    return config


class ProcessingConfiguration(configbase.ProcessingConfig):
    VERSION = 1

    show_data_plot = configbase.BoolParameter(
            label="Show data",
            default_value=True,
            updateable=True,
            order=0,
            )

    show_speed_plot = configbase.BoolParameter(
            label="Show speed on FFT y-axis",
            default_value=False,
            updateable=True,
            order=10,
            )


get_processing_config = ProcessingConfiguration


class Processor:
    def __init__(self, sensor_config, processing_config, session_info):
        pass

    def process(self, sweep):
        zero_mean_sweep = sweep - sweep.mean(axis=0, keepdims=True)
        fft = np.fft.rfft(zero_mean_sweep.T * np.hanning(sweep.shape[0]), axis=1)
        abs_fft = np.abs(fft)

        return {
            "sweep": sweep,
            "abs_fft": abs_fft,
        }


class PGUpdater:
    def __init__(self, sensor_config, processing_config, session_info):
        self.processing_config = processing_config

        self.stepsize = sensor_config.stepsize
        self.num_subsweeps = sensor_config.number_of_subsweeps
        self.subsweep_rate = session_info["actual_subsweep_rate"]
        self.depths = get_range_depths(sensor_config, session_info)
        self.actual_stepsize_m = session_info["actual_stepsize"]
        self.num_depths = self.depths.size
        self.f_res = self.subsweep_rate / self.num_subsweeps
        self.fft_x_scale = 100 * self.actual_stepsize_m

        self.smooth_max_f = self.subsweep_rate / self.num_subsweeps

        self.setup_is_done = False

    def setup(self, win):
        self.plots = []
        self.curves = []
        for i in range(self.num_depths):
            title = "{:.0f} cm".format(100 * self.depths[i])
            plot = win.addPlot(row=0, col=i, title=title)
            plot.showGrid(x=True, y=True)
            plot.setYRange(-2**15, 2**15)
            plot.hideAxis("left")
            plot.hideAxis("bottom")
            plot.plot(np.arange(self.num_subsweeps), np.zeros(self.num_subsweeps))
            curve = plot.plot(pen=utils.pg_pen_cycler())
            self.plots.append(plot)
            self.curves.append(curve)

        self.ft_plot = win.addPlot(row=1, col=0, colspan=self.num_depths)
        self.ft_im = pg.ImageItem(autoDownsample=True)
        self.ft_im.setLookupTable(utils.pg_mpl_cmap("viridis"))
        self.ft_plot.addItem(self.ft_im)
        self.ft_plot.setLabel("bottom", "Depth (cm)")
        self.ft_plot.getAxis("bottom").setTickSpacing(6 * self.stepsize, 6)

        self.smooth_max = utils.SmoothMax(
                self.smooth_max_f,
                tau_grow=0,
                tau_decay=0.5,
                hysteresis=0.1,
                )

        self.setup_is_done = True
        self.update_processing_config()

    def update_processing_config(self, processing_config=None):
        if processing_config is None:
            processing_config = self.processing_config
        else:
            self.processing_config = processing_config

        if not self.setup_is_done:
            return

        for plot in self.plots:
            plot.setVisible(self.processing_config.show_data_plot)

        half_wavelength = 2.445e-3
        self.ft_im.resetTransform()
        self.ft_im.translate(100 * (self.depths[0] - self.actual_stepsize_m / 2), 0)
        if self.processing_config.show_speed_plot:
            self.ft_plot.setLabel("left", "Speed (m/s)")
            self.ft_im.scale(self.fft_x_scale, self.f_res * half_wavelength)
        else:
            self.ft_plot.setLabel("left", "Frequency (kHz)")
            self.ft_im.scale(self.fft_x_scale, self.f_res * 1e-3)

    def update(self, data):
        frame = data["sweep"]

        for i, ys in enumerate(frame.T):
            self.curves[i].setData(ys)

        m = np.max(data["abs_fft"])
        m = max(m, 1e4)
        m = self.smooth_max.update(m)
        self.ft_im.updateImage(data["abs_fft"], levels=(0, m * 1.05))


def get_range_depths(sensor_config, session_info):
    range_start = session_info["actual_range_start"]
    range_end = range_start + session_info["actual_range_length"]
    num_depths = session_info["data_length"] // sensor_config.number_of_subsweeps
    return np.linspace(range_start, range_end, num_depths)


if __name__ == "__main__":
    main()
