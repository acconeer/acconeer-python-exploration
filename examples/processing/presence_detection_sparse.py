import numpy as np
import pyqtgraph as pg
from numpy import cos, pi, sqrt, square
from scipy.special import binom

from PyQt5 import QtCore

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
    config.sampling_mode = et.configs.SparseServiceConfig.SamplingMode.B
    config.range_interval = [0.3, 1.3]
    config.update_rate = 80
    config.sweeps_per_frame = 32
    config.hw_accelerated_average_samples = 60
    return config


class ProcessingConfiguration(et.configbase.ProcessingConfig):
    VERSION = 5

    detection_threshold = et.configbase.FloatParameter(
        label="Detection threshold",
        default_value=1.5,
        limits=(0, 5),
        updateable=True,
        order=0,
        help='Level at which the detector output is considered as "present".',
    )

    inter_frame_fast_cutoff = et.configbase.FloatParameter(
        label="Inter fast cutoff freq.",
        unit="Hz",
        default_value=20.0,
        limits=(1, 100),
        logscale=True,
        updateable=True,
        order=10,
        help=(
            "Cutoff frequency of the low pass filter for the fast filtered sweep mean."
            " No filtering is applied if the cutoff is set over half the frame rate"
            " (Nyquist limit)."
        ),
    )

    inter_frame_slow_cutoff = et.configbase.FloatParameter(
        label="Inter slow cutoff freq.",
        unit="Hz",
        default_value=0.2,
        limits=(0.01, 1),
        logscale=True,
        updateable=True,
        order=20,
        help="Cutoff frequency of the low pass filter for the slow filtered sweep mean.",
    )

    inter_frame_deviation_time_const = et.configbase.FloatParameter(
        label="Inter deviation time const.",
        unit="s",
        default_value=0.5,
        limits=(0.01, 30),
        logscale=True,
        updateable=True,
        order=30,
        help=(
            "Time constant of the low pass filter for the (inter-frame) deviation between"
            " fast and slow."
        ),
    )

    intra_frame_time_const = et.configbase.FloatParameter(
        label="Intra time const.",
        unit="s",
        default_value=0.15,
        limits=(0, 0.5),
        updateable=True,
        order=40,
        help="Time constant for the intra frame part.",
    )

    intra_frame_weight = et.configbase.FloatParameter(
        label="Intra weight",
        default_value=0.6,
        limits=(0, 1),
        updateable=True,
        order=50,
        help=(
            "The weight of the intra-frame part in the final output. A value of 1 corresponds"
            " to only using the intra-frame part and a value of 0 corresponds to only using"
            " the inter-frame part."
        ),
    )

    output_time_const = et.configbase.FloatParameter(
        label="Output time const.",
        unit="s",
        default_value=0.5,
        limits=(0.01, 30),
        logscale=True,
        updateable=True,
        order=60,
        help="Time constant of the low pass filter for the detector output."
    )

    show_data = et.configbase.BoolParameter(
        label="Show data scatter plot",
        default_value=True,
        updateable=True,
        order=100,
        help=(
            "Show the plot of the current data frame along with the fast and slow filtered"
            " mean sweep (used in the inter-frame part)."
        ),
    )

    show_noise = et.configbase.BoolParameter(
        label="Show noise",
        default_value=False,
        updateable=True,
        order=110,
        help="Show the noise estimation plot.",
        category=et.configbase.Category.ADVANCED,
    )

    show_depthwise_output = et.configbase.BoolParameter(
        label="Show depthwise presence",
        default_value=True,
        updateable=True,
        order=120,
        help="Show the depthwise presence output plot.",
    )

    show_sectors = et.configbase.BoolParameter(
        label="Show distance sectors",
        default_value=False,
        updateable=True,
        order=130,
    )

    history_plot_ceiling = et.configbase.FloatParameter(
        label="Presence score plot ceiling",
        default_value=10.0,
        decimals=1,
        limits=(1, 100),
        logscale=True,
        updateable=True,
        optional=True,
        optional_label="Fixed",
        order=190,
        help="The highest presence score that will be plotted.",
        category=et.configbase.Category.ADVANCED,
    )

    history_length_s = et.configbase.FloatParameter(
        label="History length",
        unit="s",
        default_value=5,
        limits=(1, 20),
        decimals=0,
        order=200,
        category=et.configbase.Category.ADVANCED,
    )

    def check_sensor_config(self, conf):
        alerts = []

        if conf.update_rate is None:
            alerts.append(et.configbase.Error("update_rate", "Must be set"))

        if not conf.sweeps_per_frame > 3:
            alerts.append(et.configbase.Error("sweeps_per_frame", "Must be > 3"))

        return alerts


get_processing_config = ProcessingConfiguration


class Processor:
    # lp(f): low pass (filtered)
    # cut: cutoff frequency [Hz]
    # tc: time constant [s]
    # sf: smoothing factor [dimensionless]

    def __init__(self, sensor_config, processing_config, session_info):
        self.sweeps_per_frame = sensor_config.sweeps_per_frame
        self.depths = et.utils.get_range_depths(sensor_config, session_info)
        self.num_depths = self.depths.size
        self.f = sensor_config.update_rate

        # Fixed parameters
        self.noise_est_diff_order = 3
        self.depth_filter_length = 3
        noise_tc = 1.0

        assert sensor_config.update_rate is not None
        assert self.sweeps_per_frame > self.noise_est_diff_order

        self.noise_sf = self.tc_to_sf(noise_tc, self.f)

        nd = self.noise_est_diff_order
        self.noise_norm_factor = np.sqrt(np.sum(np.square(binom(nd, np.arange(nd + 1)))))

        self.fast_lp_mean_sweep = np.zeros(self.num_depths)
        self.slow_lp_mean_sweep = np.zeros(self.num_depths)
        self.lp_inter_dev = np.zeros(self.num_depths)
        self.lp_intra_dev = np.zeros(self.num_depths)
        self.lp_noise = np.zeros(self.num_depths)

        self.presence_score = 0
        self.presence_distance_index = 0
        self.presence_distance = 0

        self.presence_history = np.zeros(int(round(self.f * processing_config.history_length_s)))
        self.update_index = 0

        self.update_processing_config(processing_config)

    def update_processing_config(self, processing_config):
        self.threshold = processing_config.detection_threshold
        self.intra_weight = processing_config.intra_frame_weight
        self.inter_weight = 1.0 - self.intra_weight

        self.fast_sf = self.cutoff_to_sf(
            processing_config.inter_frame_fast_cutoff, self.f)
        self.slow_sf = self.cutoff_to_sf(
            processing_config.inter_frame_slow_cutoff, self.f)
        self.inter_dev_sf = self.tc_to_sf(
            processing_config.inter_frame_deviation_time_const, self.f)
        self.intra_sf = self.tc_to_sf(
            processing_config.intra_frame_time_const, self.f)
        self.output_sf = self.tc_to_sf(
            processing_config.output_time_const, self.f)

    def cutoff_to_sf(self, fc, fs):  # cutoff frequency to smoothing factor conversion
        if fc > 0.5 * fs:
            return 0.0

        cos_w = cos(2.0 * pi * (fc / fs))
        return 2.0 - cos_w - sqrt(square(cos_w) - 4.0 * cos_w + 3.0)

    def tc_to_sf(self, tc, fs):  # time constant to smoothing factor conversion
        if tc <= 0.0:
            return 0.0

        return np.exp(-1.0 / (tc * fs))

    def dynamic_sf(self, static_sf):
        return min(static_sf, 1.0 - 1.0 / (1.0 + self.update_index))

    def abs_dev(self, a, axis=None, ddof=0, subtract_mean=True):
        if subtract_mean:
            a = a - a.mean(axis=axis, keepdims=True)

        if axis is None:
            n = a.size
        else:
            n = a.shape[axis]

        assert ddof >= 0
        assert n > ddof

        return np.mean(np.abs(a), axis=axis) * sqrt(n / (n - ddof))

    def depth_filter(self, a):
        b = np.ones(self.depth_filter_length) / self.depth_filter_length

        if a.size >= b.size:
            return np.correlate(a, b, mode="same")
        else:
            pad_width = int(np.ceil((b.size - a.size) / 2))
            a = np.pad(a, pad_width, "constant")
            return np.correlate(a, b, mode="same")[pad_width: -pad_width]

    def process(self, frame):
        # Noise estimation

        nd = self.noise_est_diff_order
        noise = self.abs_dev(np.diff(frame, n=nd, axis=0), axis=0, subtract_mean=False)
        noise /= self.noise_norm_factor
        sf = self.dynamic_sf(self.noise_sf)
        self.lp_noise = sf * self.lp_noise + (1.0 - sf) * noise

        # Intra-frame part

        sweep_dev = self.abs_dev(frame, axis=0, ddof=1)

        sf = self.dynamic_sf(self.intra_sf)
        self.lp_intra_dev = sf * self.lp_intra_dev + (1.0 - sf) * sweep_dev

        norm_lp_intra_dev = np.divide(
            self.lp_intra_dev,
            self.lp_noise,
            out=np.zeros(self.num_depths),
            where=(self.lp_noise > 1.0),
        )

        intra = self.depth_filter(norm_lp_intra_dev)

        # Inter-frame part

        mean_sweep = frame.mean(axis=0)

        sf = self.dynamic_sf(self.fast_sf)
        self.fast_lp_mean_sweep = sf * self.fast_lp_mean_sweep + (1.0 - sf) * mean_sweep

        sf = self.dynamic_sf(self.slow_sf)
        self.slow_lp_mean_sweep = sf * self.slow_lp_mean_sweep + (1.0 - sf) * mean_sweep

        inter_dev = np.abs(self.fast_lp_mean_sweep - self.slow_lp_mean_sweep)
        sf = self.dynamic_sf(self.inter_dev_sf)
        self.lp_inter_dev = sf * self.lp_inter_dev + (1.0 - sf) * inter_dev

        norm_lp_dev = np.divide(
            self.lp_inter_dev,
            self.lp_noise,
            out=np.zeros_like(self.lp_inter_dev),
            where=(self.lp_noise > 1.0),
        )

        norm_lp_dev *= np.sqrt(self.sweeps_per_frame)

        inter = self.depth_filter(norm_lp_dev)

        # Detector output

        depthwise_presence = self.inter_weight * inter + self.intra_weight * intra

        max_depthwise_presence = np.max(depthwise_presence)

        sf = self.output_sf  # no dynamic filter for the output
        self.presence_score = sf * self.presence_score + (1.0 - sf) * max_depthwise_presence

        presence_detected = self.presence_score > self.threshold

        self.presence_history = np.roll(self.presence_history, -1)
        self.presence_history[-1] = self.presence_score

        if max_depthwise_presence > self.threshold:
            self.presence_distance_index = np.argmax(depthwise_presence)
            self.presence_distance = self.depths[self.presence_distance_index]

        out_data = {
            "frame": frame,
            "fast": self.fast_lp_mean_sweep,
            "slow": self.slow_lp_mean_sweep,
            "noise": self.lp_noise,
            "inter": inter * self.inter_weight,
            "intra": intra * self.intra_weight,
            "depthwise_presence": depthwise_presence,
            "presence_distance_index": self.presence_distance_index,
            "presence_distance": self.presence_distance,
            "presence_history": self.presence_history,
            "presence_detected": presence_detected,
        }

        self.update_index += 1

        return out_data


class PGUpdater:
    def __init__(self, sensor_config, processing_config, session_info):
        self.sensor_config = sensor_config
        self.processing_config = processing_config

        self.history_length_s = processing_config.history_length_s
        self.depths = et.utils.get_range_depths(sensor_config, session_info)

        max_num_of_sectors = max(6, self.depths.size // 3)
        self.sector_size = max(1, -(-self.depths.size // max_num_of_sectors))
        self.num_sectors = -(-self.depths.size // self.sector_size)
        self.sector_offset = (self.num_sectors * self.sector_size - self.depths.size) // 2

        self.setup_is_done = False

    def setup(self, win):
        win.setWindowTitle("Acconeer presence detection example")

        self.limit_lines = []
        dashed_pen = pg.mkPen("k", width=2.5, style=QtCore.Qt.DashLine)

        # Data plot

        self.data_plot = win.addPlot(
            row=0,
            col=0,
            title="Frame (blue), fast (orange), and slow (green)",
        )
        self.data_plot.setMenuEnabled(False)
        self.data_plot.setMouseEnabled(x=False, y=False)
        self.data_plot.hideButtons()
        self.data_plot.showGrid(x=True, y=True)
        self.data_plot.setLabel("bottom", "Depth (m)")
        self.data_plot.setLabel("left", "Amplitude")
        self.data_plot.setYRange(0, 2**16)
        self.frame_scatter = pg.ScatterPlotItem(
            size=10,
            brush=et.utils.pg_brush_cycler(0),
        )
        self.fast_scatter = pg.ScatterPlotItem(
            size=10,
            brush=et.utils.pg_brush_cycler(1),
        )
        self.slow_scatter = pg.ScatterPlotItem(
            size=10,
            brush=et.utils.pg_brush_cycler(2),
        )
        self.data_plot.addItem(self.frame_scatter)
        self.data_plot.addItem(self.fast_scatter)
        self.data_plot.addItem(self.slow_scatter)
        self.frame_smooth_limits = et.utils.SmoothLimits(self.sensor_config.update_rate)

        # Noise estimation plot

        self.noise_plot = win.addPlot(
            row=1,
            col=0,
            title="Noise",
        )
        self.noise_plot.setMenuEnabled(False)
        self.noise_plot.setMouseEnabled(x=False, y=False)
        self.noise_plot.hideButtons()
        self.noise_plot.showGrid(x=True, y=True)
        self.noise_plot.setLabel("bottom", "Depth (m)")
        self.noise_plot.setLabel("left", "Amplitude")
        self.noise_curve = self.noise_plot.plot(pen=et.utils.pg_pen_cycler())
        self.noise_smooth_max = et.utils.SmoothMax(self.sensor_config.update_rate)

        # Depthwise presence plot

        self.move_plot = win.addPlot(
            row=2,
            col=0,
            title="Depthwise presence",
        )
        self.move_plot.setMenuEnabled(False)
        self.move_plot.setMouseEnabled(x=False, y=False)
        self.move_plot.hideButtons()
        self.move_plot.showGrid(x=True, y=True)
        self.move_plot.setLabel("bottom", "Depth (m)")
        self.move_plot.setLabel("left", "Norm. ampl.")
        zero_curve = self.move_plot.plot(self.depths, np.zeros_like(self.depths))
        self.inter_curve = self.move_plot.plot()
        self.total_curve = self.move_plot.plot()
        self.move_smooth_max = et.utils.SmoothMax(
            self.sensor_config.update_rate,
            tau_decay=1.0,
            tau_grow=0.25,
        )

        self.move_depth_line = pg.InfiniteLine(pen=pg.mkPen("k", width=1.5))
        self.move_depth_line.hide()
        self.move_plot.addItem(self.move_depth_line)
        limit_line = pg.InfiniteLine(angle=0, pen=dashed_pen)
        self.move_plot.addItem(limit_line)
        self.limit_lines.append(limit_line)

        fbi = pg.FillBetweenItem(
            zero_curve,
            self.inter_curve,
            brush=et.utils.pg_brush_cycler(0),
        )
        self.move_plot.addItem(fbi)

        fbi = pg.FillBetweenItem(
            self.inter_curve,
            self.total_curve,
            brush=et.utils.pg_brush_cycler(1),
        )
        self.move_plot.addItem(fbi)

        # Presence history plot

        self.move_hist_plot = pg.PlotItem(title="Presence history")
        self.move_hist_plot.setMenuEnabled(False)
        self.move_hist_plot.setMouseEnabled(x=False, y=False)
        self.move_hist_plot.hideButtons()
        self.move_hist_plot.showGrid(x=True, y=True)
        self.move_hist_plot.setLabel("bottom", "Time (s)")
        self.move_hist_plot.setLabel("left", "Score")
        self.move_hist_plot.setXRange(-self.history_length_s, 0)
        self.history_smooth_max = et.utils.SmoothMax(self.sensor_config.update_rate)
        self.move_hist_plot.setYRange(0, 10)

        self.move_hist_curve = self.move_hist_plot.plot(pen=et.utils.pg_pen_cycler())
        limit_line = pg.InfiniteLine(angle=0, pen=dashed_pen)
        self.move_hist_plot.addItem(limit_line)
        self.limit_lines.append(limit_line)

        self.present_html_format = '<div style="text-align: center">' \
                                   '<span style="color: #FFFFFF;font-size:15pt;">' \
                                   "{}</span></div>"
        not_present_html = '<div style="text-align: center">' \
                           '<span style="color: #FFFFFF;font-size:15pt;">' \
                           "{}</span></div>".format("No presence detected")
        self.present_text_item = pg.TextItem(
            fill=pg.mkColor(0xff, 0x7f, 0x0e, 200),
            anchor=(0.5, 0),
        )
        self.not_present_text_item = pg.TextItem(
            html=not_present_html,
            fill=pg.mkColor(0x1f, 0x77, 0xb4, 180),
            anchor=(0.5, 0),
        )

        self.move_hist_plot.addItem(self.present_text_item)
        self.move_hist_plot.addItem(self.not_present_text_item)
        self.present_text_item.hide()
        self.not_present_text_item.hide()

        # Sector plot

        self.sector_plot = pg.PlotItem()
        self.sector_plot.setAspectLocked()
        self.sector_plot.hideAxis("left")
        self.sector_plot.hideAxis("bottom")
        self.sectors = []

        pen = pg.mkPen("k", width=1)
        span_deg = 25
        for r in np.flip(np.arange(self.num_sectors) + 1):
            sector = pg.QtGui.QGraphicsEllipseItem(-r, -r, r * 2, r * 2)
            sector.setStartAngle(-16 * span_deg)
            sector.setSpanAngle(16 * span_deg * 2)
            sector.setPen(pen)
            self.sector_plot.addItem(sector)
            self.sectors.append(sector)

        self.sectors.reverse()

        sublayout = win.addLayout(row=3, col=0)
        sublayout.layout.setColumnStretchFactor(0, 2)
        sublayout.addItem(self.move_hist_plot, col=0)
        sublayout.addItem(self.sector_plot, col=1)

        self.setup_is_done = True
        self.update_processing_config()

    def update_processing_config(self, processing_config=None):
        if processing_config is None:
            processing_config = self.processing_config
        else:
            self.processing_config = processing_config

        if not self.setup_is_done:
            return

        self.data_plot.setVisible(self.processing_config.show_data)
        self.noise_plot.setVisible(self.processing_config.show_noise)
        self.move_plot.setVisible(self.processing_config.show_depthwise_output)
        self.sector_plot.setVisible(self.processing_config.show_sectors)

        for line in self.limit_lines:
            line.setPos(processing_config.detection_threshold)

    def update(self, data):
        self.frame_scatter.setData(
            np.tile(self.depths, self.sensor_config.sweeps_per_frame),
            data["frame"].flatten(),
        )

        self.fast_scatter.setData(self.depths, data["fast"])
        self.slow_scatter.setData(self.depths, data["slow"])
        self.data_plot.setYRange(*self.frame_smooth_limits.update(data["frame"]))

        noise = data["noise"]
        self.noise_curve.setData(self.depths, noise)
        self.noise_plot.setYRange(0, self.noise_smooth_max.update(noise))

        movement_x = data["presence_distance"]

        move_ys = data["depthwise_presence"]
        self.inter_curve.setData(self.depths, data["inter"])
        self.total_curve.setData(self.depths, move_ys)
        m = self.move_smooth_max.update(np.max(move_ys))
        m = max(m, 2 * self.processing_config.detection_threshold)
        self.move_plot.setYRange(0, m)
        self.move_depth_line.setPos(movement_x)
        self.move_depth_line.setVisible(bool(data["presence_detected"]))

        move_hist_ys = data["presence_history"]
        move_hist_xs = np.linspace(-self.history_length_s, 0, len(move_hist_ys))

        m_hist = max(np.max(move_hist_ys), self.processing_config.detection_threshold * 1.05)
        m_hist = self.history_smooth_max.update(m_hist)

        if self.processing_config.history_plot_ceiling is not None:
            self.move_hist_plot.setYRange(0, self.processing_config.history_plot_ceiling)
            self.move_hist_curve.setData(
                move_hist_xs,
                np.minimum(move_hist_ys, self.processing_config.history_plot_ceiling),
            )
            self.set_present_text_y_pos(self.processing_config.history_plot_ceiling)
        else:
            self.move_hist_plot.setYRange(0, m_hist)
            self.move_hist_curve.setData(move_hist_xs, move_hist_ys)
            self.set_present_text_y_pos(m_hist)

        if data["presence_detected"]:
            present_text = "Presence detected at {:.0f} cm".format(movement_x * 100)
            present_html = self.present_html_format.format(present_text)
            self.present_text_item.setHtml(present_html)

            self.present_text_item.show()
            self.not_present_text_item.hide()
        else:
            self.present_text_item.hide()
            self.not_present_text_item.show()

        brush = et.utils.pg_brush_cycler(0)
        for sector in self.sectors:
            sector.setBrush(brush)

        if data["presence_detected"]:
            index = (data["presence_distance_index"] + self.sector_offset) // self.sector_size
            self.sectors[index].setBrush(et.utils.pg_brush_cycler(1))

    def set_present_text_y_pos(self, y):
        self.present_text_item.setPos(-self.history_length_s / 2, 0.95 * y)
        self.not_present_text_item.setPos(-self.history_length_s / 2, 0.95 * y)


if __name__ == "__main__":
    main()
