from enum import Enum

import numpy as np
import pyqtgraph as pg
from scipy.signal.windows import hann

from PyQt5 import QtCore

import acconeer.exptool as et


HALF_WAVELENGTH = 2.445e-3  # m
HISTORY_LENGTH = 2.0  # s
EST_VEL_HISTORY_LENGTH = HISTORY_LENGTH  # s
SD_HISTORY_LENGTH = HISTORY_LENGTH  # s
NUM_SAVED_SEQUENCES = 100
SEQUENCE_TIMEOUT_LENGTH = 0.5  # s
OVERLAP = True


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
    config.profile = et.configs.SparseServiceConfig.Profile.PROFILE_4
    config.sampling_mode = et.configs.SparseServiceConfig.SamplingMode.A
    config.range_interval = [0.36, 0.54]
    config.downsampling_factor = 3
    config.sweeps_per_frame = 512
    config.hw_accelerated_average_samples = 60
    return config


class ProcessingConfiguration(et.configbase.ProcessingConfig):
    VERSION = 4

    class SpeedUnit(Enum):
        METER_PER_SECOND = ("m/s", 1)
        KILOMETERS_PER_HOUR = ("km/h", 3.6)
        MILES_PER_HOUR = ("mph", 2.237)

        @property
        def label(self):
            return self.value[0]

        @property
        def scale(self):
            return self.value[1]

    threshold = et.configbase.FloatParameter(
        label="Threshold",
        default_value=4.0,
        limits=(1, 100),
        decimals=2,
        updateable=True,
        logscale=True,
        order=0,
    )

    min_speed = et.configbase.FloatParameter(
        label="Minimum speed",
        unit="m/s",
        default_value=0.5,
        limits=(0, 5),
        decimals=1,
        updateable=True,
        order=10,
    )

    fft_oversampling_factor = et.configbase.IntParameter(
        label="FFT oversampling factor",
        default_value=1,
        valid_values=[1, 2, 4, 8],
        updateable=False,
        order=11,
    )

    shown_speed_unit = et.configbase.EnumParameter(
        label="Speed unit",
        default_value=SpeedUnit.METER_PER_SECOND,
        enum=SpeedUnit,
        updateable=True,
        order=100,
    )

    show_data_plot = et.configbase.BoolParameter(
        label="Show data",
        default_value=False,
        updateable=True,
        order=110,
    )

    show_sd_plot = et.configbase.BoolParameter(
        label="Show spectral density",
        default_value=True,
        updateable=True,
        order=120,
    )

    show_vel_history_plot = et.configbase.BoolParameter(
        label="Show speed history",
        default_value=True,
        updateable=True,
        order=130,
    )

    num_shown_sequences = et.configbase.IntParameter(
        label="Number of history bars",
        default_value=10,
        limits=(1, NUM_SAVED_SEQUENCES),
        updateable=True,
        order=150,
    )


get_processing_config = ProcessingConfiguration


class Processor:
    def __init__(self, sensor_config, processing_config, session_info):
        self.sweeps_per_frame = sensor_config.sweeps_per_frame
        sweep_rate = session_info["sweep_rate"]
        est_frame_rate = sweep_rate / self.sweeps_per_frame
        self.depths = et.utils.get_range_depths(sensor_config, session_info)

        self.fft_length = (self.sweeps_per_frame // 2) * processing_config.fft_oversampling_factor
        self.num_noise_est_bins = 3
        noise_est_tc = 1.0

        self.sequence_timeout_count = int(round(est_frame_rate * SEQUENCE_TIMEOUT_LENGTH))
        est_vel_history_size = int(round(est_frame_rate * EST_VEL_HISTORY_LENGTH))
        sd_history_size = int(round(est_frame_rate * SD_HISTORY_LENGTH))
        self.noise_est_sf = self.tc_to_sf(noise_est_tc, est_frame_rate)
        self.bin_fs = np.fft.rfftfreq(self.fft_length) * sweep_rate
        self.bin_vs = self.bin_fs * HALF_WAVELENGTH

        num_bins = self.bin_fs.size
        self.nasd_history = np.zeros([sd_history_size, num_bins])
        self.est_vel_history = np.full(est_vel_history_size, np.nan)
        self.belongs_to_last_sequence = np.zeros(est_vel_history_size, dtype=bool)
        self.noise_est = 0
        self.current_sequence_idle = self.sequence_timeout_count + 1
        self.sequence_vels = np.zeros(NUM_SAVED_SEQUENCES)
        self.update_idx = 0

        self.update_processing_config(processing_config)

    def update_processing_config(self, processing_config):
        self.min_speed = processing_config.min_speed
        self.threshold = processing_config.threshold

    def tc_to_sf(self, tc, fs):
        if tc <= 0.0:
            return 0.0

        return np.exp(-1.0 / (tc * fs))

    def dynamic_sf(self, static_sf):
        return min(static_sf, 1.0 - 1.0 / (1.0 + self.update_idx))

    def process(self, frame):
        # Basic speed estimate using Welch's method

        zero_mean_frame = frame - frame.mean(axis=0, keepdims=True)
        segment_size = self.sweeps_per_frame // 2  # Segment size = 50 % of data length
        psd_length = self.fft_length // 2 + 1

        num_base_segments = self.sweeps_per_frame // segment_size

        if OVERLAP:  # Overlap is 50% of the segment size
            num_segments = 2 * num_base_segments - 1
        else:
            num_segments = num_base_segments

        window = hann(segment_size, sym=False)
        window_norm = np.sum(window**2)

        fft_segments = np.empty((num_segments, psd_length, len(self.depths)))

        for i in range(num_segments):
            if OVERLAP:
                offset_segment = i * segment_size // 2
            else:
                offset_segment = i * segment_size

            current_segment = zero_mean_frame[offset_segment:offset_segment + segment_size]

            windowed_segment = current_segment * window[:, None]

            fft_segments[i] = np.square(np.abs(np.fft.rfft(
                windowed_segment,
                self.fft_length,
                axis=0,
            ))) / window_norm  # rfft automatically pads if n<nfft

        # Add FFTs of different segments and average to decrease FFT variance

        psds = np.mean(fft_segments, axis=0)

        psds[2:psd_length - 1] *= 2  # Double frequencies except DC and Nyquist

        psd = np.max(psds, axis=1)  # Power Spectral Density
        asd = np.sqrt(psd)  # Amplitude Spectral Density

        inst_noise_est = np.mean(asd[(-self.num_noise_est_bins - 1):-1])
        sf = self.dynamic_sf(self.noise_est_sf)  # Smoothing factor
        self.noise_est = sf * self.noise_est + (1.0 - sf) * inst_noise_est

        nasd = asd / self.noise_est  # Normalized Amplitude Spectral Density

        over = nasd > self.threshold
        est_idx = np.where(over)[0][-1] if np.any(over) else np.nan

        if est_idx > 0:  # evaluates to false if nan
            est_vel = self.bin_vs[est_idx]
        else:
            est_vel = np.nan

        if est_vel < self.min_speed:  # evaluates to false if nan
            est_vel = np.nan

        # Sequence

        self.belongs_to_last_sequence = np.roll(self.belongs_to_last_sequence, -1)

        if np.isnan(est_vel):
            self.current_sequence_idle += 1
        else:
            if self.current_sequence_idle > self.sequence_timeout_count:
                self.sequence_vels = np.roll(self.sequence_vels, -1)
                self.sequence_vels[-1] = est_vel
                self.belongs_to_last_sequence[:] = False

            self.current_sequence_idle = 0
            self.belongs_to_last_sequence[-1] = True

            if est_vel > self.sequence_vels[-1]:
                self.sequence_vels[-1] = est_vel

        # Data for plots

        self.est_vel_history = np.roll(self.est_vel_history, -1, axis=0)
        self.est_vel_history[-1] = est_vel

        if np.all(np.isnan(self.est_vel_history)):
            output_vel = None
        else:
            output_vel = np.nanmax(self.est_vel_history)

        self.nasd_history = np.roll(self.nasd_history, -1, axis=0)
        self.nasd_history[-1] = nasd

        nasd_temporal_max = np.max(self.nasd_history, axis=0)

        temporal_max_threshold = self.threshold

        self.update_idx += 1

        return {
            "frame": frame,
            "nasd": nasd,
            "nasd_temporal_max": nasd_temporal_max,
            "temporal_max_threshold": temporal_max_threshold,
            "vel_history": self.est_vel_history,
            "vel": output_vel,
            "sequence_vels": self.sequence_vels,
            "belongs_to_last_sequence": self.belongs_to_last_sequence,
        }


class PGUpdater:
    def __init__(self, sensor_config, processing_config, session_info):
        self.processing_config = processing_config

        self.sweeps_per_frame = sensor_config.sweeps_per_frame
        self.sweep_rate = session_info["sweep_rate"]
        self.depths = et.utils.get_range_depths(sensor_config, session_info)
        self.num_depths = self.depths.size
        self.est_update_rate = self.sweep_rate / self.sweeps_per_frame

        self.num_shown_sequences = processing_config.num_shown_sequences
        fft_length = (self.sweeps_per_frame // 2) * processing_config.fft_oversampling_factor
        self.bin_vs = np.fft.rfftfreq(fft_length) * self.sweep_rate * HALF_WAVELENGTH
        self.dt = 1.0 / self.est_update_rate

        self.setup_is_done = False

    def setup(self, win):
        # Data plots

        self.data_plots = []
        self.data_curves = []
        for i in range(self.num_depths):
            title = "{:.0f} cm".format(100 * self.depths[i])
            plot = win.addPlot(row=0, col=i, title=title)
            plot.setMenuEnabled(False)
            plot.setMouseEnabled(x=False, y=False)
            plot.hideButtons()
            plot.showGrid(x=True, y=True)
            plot.setYRange(0, 2**16)
            plot.hideAxis("left")
            plot.hideAxis("bottom")
            plot.plot(np.arange(self.sweeps_per_frame), 2**15 * np.ones(self.sweeps_per_frame))
            curve = plot.plot(pen=et.utils.pg_pen_cycler())
            self.data_plots.append(plot)
            self.data_curves.append(curve)

        # Spectral density plot

        self.sd_plot = win.addPlot(row=1, col=0, colspan=self.num_depths)
        self.sd_plot.setMenuEnabled(False)
        self.sd_plot.setMouseEnabled(x=False, y=False)
        self.sd_plot.hideButtons()
        self.sd_plot.setLabel("left", "Normalized PSD (dB)")
        self.sd_plot.showGrid(x=True, y=True)
        self.sd_curve = self.sd_plot.plot(pen=et.utils.pg_pen_cycler())
        dashed_pen = pg.mkPen("k", width=2, style=QtCore.Qt.DashLine)
        self.sd_threshold_line = pg.InfiniteLine(angle=0, pen=dashed_pen)
        self.sd_plot.addItem(self.sd_threshold_line)

        self.smooth_max = et.utils.SmoothMax(
            self.est_update_rate,
            tau_decay=0.5,
            tau_grow=0,
            hysteresis=0.2,
        )

        # Rolling speed plot

        self.vel_plot = pg.PlotItem()
        self.vel_plot.setMenuEnabled(False)
        self.vel_plot.setMouseEnabled(x=False, y=False)
        self.vel_plot.hideButtons()
        self.vel_plot.setLabel("bottom", "Time (s)")
        self.vel_plot.showGrid(x=True, y=True)
        self.vel_plot.setXRange(-EST_VEL_HISTORY_LENGTH, 0)
        self.vel_max_line = pg.InfiniteLine(angle=0, pen=pg.mkPen("k", width=1))
        self.vel_plot.addItem(self.vel_max_line)
        self.vel_scatter = pg.ScatterPlotItem(size=8)
        self.vel_plot.addItem(self.vel_scatter)

        self.vel_html_fmt = '<span style="color:#000;font-size:24pt;">{:.1f} {}</span>'
        self.vel_text_item = pg.TextItem(anchor=(0.5, 0))
        self.vel_plot.addItem(self.vel_text_item)

        # Sequence speed plot

        self.sequences_plot = pg.PlotItem()
        self.sequences_plot.setMenuEnabled(False)
        self.sequences_plot.setMouseEnabled(x=False, y=False)
        self.sequences_plot.hideButtons()
        self.sequences_plot.setLabel("bottom", "History")
        self.sequences_plot.showGrid(y=True)
        self.sequences_plot.setXRange(-self.num_shown_sequences + 0.5, 0.5)
        tmp = np.flip(np.arange(NUM_SAVED_SEQUENCES) == 0)
        brushes = [pg.mkBrush(et.utils.color_cycler(n)) for n in tmp]
        self.bar_graph = pg.BarGraphItem(
            x=np.arange(-NUM_SAVED_SEQUENCES, 0) + 1,
            height=np.zeros(NUM_SAVED_SEQUENCES),
            width=0.8,
            brushes=brushes,
        )
        self.sequences_plot.addItem(self.bar_graph)

        self.sequences_text_item = pg.TextItem(anchor=(0.5, 0))
        self.sequences_plot.addItem(self.sequences_text_item)

        sublayout = win.addLayout(row=2, col=0, colspan=self.num_depths)
        sublayout.addItem(self.vel_plot, col=0)
        sublayout.addItem(self.sequences_plot, col=1)

        self.setup_is_done = True
        self.update_processing_config()

    def update_processing_config(self, processing_config=None):
        if processing_config is None:
            processing_config = self.processing_config
        else:
            self.processing_config = processing_config

        if not self.setup_is_done:
            return

        for plot in self.data_plots:
            plot.setVisible(processing_config.show_data_plot)

        self.sd_plot.setVisible(processing_config.show_sd_plot)
        self.vel_plot.setVisible(processing_config.show_vel_history_plot)

        self.unit = processing_config.shown_speed_unit
        speed_label = "Speed ({})".format(self.unit.label)
        self.sd_plot.setLabel("bottom", speed_label)
        self.vel_plot.setLabel("left", speed_label)
        self.sequences_plot.setLabel("left", speed_label)
        max_vel = self.bin_vs[-1] * self.unit.scale
        self.sd_plot.setXRange(0, max_vel)

        self.num_shown_sequences = processing_config.num_shown_sequences
        self.sequences_plot.setXRange(-self.num_shown_sequences + 0.5, 0.5)

        y_max = max_vel * 1.2
        self.vel_plot.setYRange(0, y_max)
        self.sequences_plot.setYRange(0, y_max)
        self.vel_text_item.setPos(-EST_VEL_HISTORY_LENGTH / 2, y_max)
        self.sequences_text_item.setPos(-self.num_shown_sequences / 2 + 0.5, y_max)

    def update(self, data):
        # Data plots

        for i, ys in enumerate(data["frame"].T):
            self.data_curves[i].setData(ys)

        # Spectral density plot

        psd_db = 20 * np.log10(data["nasd_temporal_max"])
        psd_threshold_db = 20 * np.log10(data["temporal_max_threshold"])
        m = self.smooth_max.update(max(2 * psd_threshold_db, np.max(psd_db)))
        self.sd_plot.setYRange(0, m)
        self.sd_curve.setData(self.bin_vs * self.unit.scale, psd_db)
        self.sd_threshold_line.setPos(psd_threshold_db)

        # Rolling speed plot

        vs = data["vel_history"] * self.unit.scale
        mask = ~np.isnan(vs)
        ts = -np.flip(np.arange(vs.size)) * self.dt
        bs = data["belongs_to_last_sequence"]
        brushes = [et.utils.pg_brush_cycler(int(b)) for b in bs[mask]]

        self.vel_scatter.setData(ts[mask], vs[mask], brush=brushes)

        v = data["vel"]
        if v:
            html = self.vel_html_fmt.format(v * self.unit.scale, self.unit.label)
            self.vel_text_item.setHtml(html)
            self.vel_text_item.show()

            self.vel_max_line.setPos(v * self.unit.scale)
            self.vel_max_line.show()
        else:
            self.vel_text_item.hide()
            self.vel_max_line.hide()

        # Sequence speed plot

        hs = data["sequence_vels"] * self.unit.scale
        self.bar_graph.setOpts(height=hs)

        if hs[-1] > 1e-3:
            html = self.vel_html_fmt.format(hs[-1], self.unit.label)
            self.sequences_text_item.setHtml(html)


if __name__ == "__main__":
    main()
