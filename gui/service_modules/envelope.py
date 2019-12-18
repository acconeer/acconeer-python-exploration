from enum import Enum

import numpy as np
import pyqtgraph as pg

from acconeer.exptool import clients, configs, utils
from acconeer.exptool.pg_process import PGProccessDiedException, PGProcess
from acconeer.exptool.structs import configbase


def main():
    args = utils.ExampleArgumentParser().parse_args()
    utils.config_logging(args)

    if args.socket_addr:
        client = clients.SocketClient(args.socket_addr)
    elif args.spi:
        client = clients.SPIClient()
    else:
        port = args.serial_port or utils.autodetect_serial_port()
        client = clients.UARTClient(port)

    client.squeeze = False

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
        info, data = client.get_next()
        plot_data = processor.process(data)

        if plot_data is not None:
            try:
                pg_process.put_data(plot_data)
            except PGProccessDiedException:
                break

    print("Disconnecting...")
    pg_process.close()
    client.disconnect()


def get_sensor_config():
    config = configs.EnvelopeServiceConfig()
    config.range_interval = [0.2, 0.8]
    config.hw_accelerated_average_samples = 15
    config.update_rate = 30
    return config


class ProcessingConfig(configbase.ProcessingConfig):
    VERSION = 1

    class BackgroundMode(Enum):
        SUBTRACT = "Subtract"
        LIMIT = "Limit"

    show_peak_depths = configbase.BoolParameter(
        label="Show peak distances",
        default_value=True,
        updateable=True,
        order=-10,
    )

    bg_buffer_length = configbase.IntParameter(
        default_value=50,
        limits=(1, 200),
        label="Background buffer length",
        order=0,
    )

    bg = configbase.ReferenceDataParameter(
        label="Background",
        order=10,
    )

    bg_mode = configbase.EnumParameter(
        label="Background mode",
        default_value=BackgroundMode.SUBTRACT,
        enum=BackgroundMode,
        updateable=True,
        order=20,
    )

    history_length = configbase.IntParameter(
        default_value=100,
        limits=(10, 1000),
        label="History length",
        order=30,
    )


get_processing_config = ProcessingConfig


class Processor:
    def __init__(self, sensor_config, processing_config, session_info):
        self.processing_config = processing_config

        self.processing_config.bg.buffered_data = None
        self.processing_config.bg.error = None

        self.depths = utils.get_range_depths(sensor_config, session_info)
        num_depths = self.depths.size
        num_sensors = len(sensor_config.sensor)

        buffer_length = self.processing_config.bg_buffer_length
        self.bg_buffer = np.zeros([buffer_length, num_sensors, num_depths])

        history_length = self.processing_config.history_length
        self.history = np.zeros([history_length, num_sensors, num_depths])

        self.data_index = 0

    def process(self, data):
        if self.data_index < self.bg_buffer.shape[0]:
            self.bg_buffer[self.data_index] = data
        if self.data_index == self.bg_buffer.shape[0] - 1:
            self.processing_config.bg.buffered_data = self.bg_buffer.mean(axis=0)

        bg = None
        output_data = data
        if self.processing_config.bg.error is None:
            loaded_bg = self.processing_config.bg.loaded_data

            if loaded_bg is None:
                pass
            elif not isinstance(loaded_bg, np.ndarray):
                self.processing_config.bg.error = "Wrong type"
            elif np.iscomplexobj(loaded_bg):
                self.processing_config.bg.error = "Wrong type (is complex)"
            elif loaded_bg.shape != data.shape:
                self.processing_config.bg.error = "Dimension mismatch"
            elif self.processing_config.bg.use:
                try:
                    subtract_mode = ProcessingConfig.BackgroundMode.SUBTRACT
                    if self.processing_config.bg_mode == subtract_mode:
                        output_data = np.maximum(0, data - loaded_bg)
                    else:
                        output_data = np.maximum(data, loaded_bg)
                except Exception:
                    self.processing_config.bg.error = "Invalid data"
                else:
                    bg = loaded_bg

        self.history = np.roll(self.history, -1, axis=0)
        self.history[-1] = output_data

        peak_ampls = [np.max(sweep) for sweep in output_data]
        peak_depths = [self.depths[np.argmax(sweep)] for sweep in output_data]
        filtered_peak_depths = [d if a > 200 else None for d, a in zip(peak_depths, peak_ampls)]

        output = {
            "output_data": output_data,
            "bg": bg,
            "history": self.history,
            "peak_depths": filtered_peak_depths,
        }

        self.data_index += 1

        return output


class PGUpdater:
    def __init__(self, sensor_config, processing_config, session_info):
        self.sensor_config = sensor_config
        self.processing_config = processing_config

        self.depths = utils.get_range_depths(sensor_config, session_info)
        self.depth_res = session_info["step_length_m"]
        self.smooth_max = utils.SmoothMax(sensor_config.update_rate)

        self.setup_is_done = False

    def setup(self, win):
        num_sensors = len(self.sensor_config.sensor)

        self.ampl_plot = win.addPlot(row=0, colspan=num_sensors)
        self.ampl_plot.setMenuEnabled(False)
        self.ampl_plot.showGrid(x=True, y=True)
        self.ampl_plot.setLabel("bottom", "Depth (m)")
        self.ampl_plot.setLabel("left", "Amplitude")
        self.ampl_plot.setXRange(*self.depths.take((0, -1)))
        self.ampl_plot.setYRange(0, 1)  # To avoid rendering bug
        self.ampl_plot.addLegend(offset=(-10, 10))

        self.ampl_curves = []
        self.bg_curves = []
        self.peak_lines = []
        for i, sensor_id in enumerate(self.sensor_config.sensor):
            legend = "Sensor {}".format(sensor_id)
            ampl_curve = self.ampl_plot.plot(pen=utils.pg_pen_cycler(i), name=legend)
            bg_curve = self.ampl_plot.plot(pen=utils.pg_pen_cycler(i, style="--"))
            color_tuple = utils.hex_to_rgb_tuple(utils.color_cycler(i))
            peak_line = pg.InfiniteLine(pen=pg.mkPen(pg.mkColor(*color_tuple, 150), width=2))
            self.ampl_plot.addItem(peak_line)
            self.ampl_curves.append(ampl_curve)
            self.bg_curves.append(bg_curve)
            self.peak_lines.append(peak_line)

        bg = pg.mkColor(0xFF, 0xFF, 0xFF, 150)
        self.peak_text = pg.TextItem(anchor=(0, 1), color="k", fill=bg)
        self.peak_text.setPos(self.depths[0], 0)
        self.peak_text.setZValue(100)
        self.ampl_plot.addItem(self.peak_text)

        rate = self.sensor_config.update_rate
        xlabel = "Sweeps" if rate is None else "Time (s)"
        x_scale = 1.0 if rate is None else 1.0 / rate
        y_scale = self.depth_res
        x_offset = -self.processing_config.history_length * x_scale
        y_offset = self.depths[0] - 0.5 * self.depth_res
        is_single_sensor = len(self.sensor_config.sensor) == 1

        self.history_plots = []
        self.history_ims = []
        for i, sensor_id in enumerate(self.sensor_config.sensor):
            title = None if is_single_sensor else "Sensor {}".format(sensor_id)
            plot = win.addPlot(row=1, col=i, title=title)
            plot.setMenuEnabled(False)
            plot.setLabel("bottom", xlabel)
            plot.setLabel("left", "Depth (m)")
            im = pg.ImageItem(autoDownsample=True)
            im.setLookupTable(utils.pg_mpl_cmap("viridis"))
            im.resetTransform()
            im.translate(x_offset, y_offset)
            im.scale(x_scale, y_scale)
            plot.addItem(im)
            self.history_plots.append(plot)
            self.history_ims.append(im)

        self.setup_is_done = True
        self.update_processing_config()

    def update_processing_config(self, processing_config=None):
        if processing_config is None:
            processing_config = self.processing_config
        else:
            self.processing_config = processing_config

        if not self.setup_is_done:
            return

        self.show_peaks = processing_config.show_peak_depths
        self.peak_text.setVisible(self.show_peaks)

        bg = processing_config.bg
        has_bg = bg.use and bg.loaded_data is not None and bg.error is None
        limit_mode = ProcessingConfig.BackgroundMode.LIMIT
        show_bg = has_bg and processing_config.bg_mode == limit_mode

        for curve in self.bg_curves:
            curve.setVisible(show_bg)

    def update(self, d):
        sweeps = d["output_data"]
        bgs = d["bg"]
        histories = d["history"]

        for i, _ in enumerate(self.sensor_config.sensor):
            self.ampl_curves[i].setData(self.depths, sweeps[i])

            if bgs is not None:
                self.bg_curves[i].setData(self.depths, bgs[i])

            peak = d["peak_depths"][i]
            if peak is not None and self.show_peaks:
                self.peak_lines[i].setPos(peak)
                self.peak_lines[i].show()
            else:
                self.peak_lines[i].hide()

            im = self.history_ims[i]
            history = histories[:, i]
            im.updateImage(history, levels=(0, 1.05 * history.max()))

        m = self.smooth_max.update(sweeps.max())
        self.ampl_plot.setYRange(0, m)

        # Update peak text item
        val_strs = ["-" if p is None else "{:5.3f} m".format(p) for p in d["peak_depths"]]
        z = zip(self.sensor_config.sensor, val_strs)
        t = "\n".join(["Sensor {}: {}".format(sid, v) for sid, v in z])
        self.peak_text.setText(t)


if __name__ == "__main__":
    main()
