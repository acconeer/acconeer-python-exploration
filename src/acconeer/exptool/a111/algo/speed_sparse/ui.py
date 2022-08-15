# Copyright (c) Acconeer AB, 2022
# All rights reserved

import numpy as np

from PySide6 import QtCore

import pyqtgraph as pg

import acconeer.exptool as et

from ._processor import ProcessingConfiguration
from .constants import EST_VEL_HISTORY_LENGTH, HALF_WAVELENGTH, NUM_SAVED_SEQUENCES


class PGUpdater:
    def __init__(self, sensor_config, processing_config, session_info):
        self.processing_config = processing_config

        self.sweeps_per_frame = sensor_config.sweeps_per_frame
        self.sweep_rate = session_info["sweep_rate"]
        self.depths = et.a111.get_range_depths(sensor_config, session_info)
        self.num_depths = self.depths.size
        self.est_update_rate = self.sweep_rate / self.sweeps_per_frame

        self.num_shown_sequences = processing_config.num_shown_sequences

        if (
            self.processing_config.processing_method
            == ProcessingConfiguration.ProcessingMethod.WELCH
        ):
            segment_length = 2 * self.sweeps_per_frame // (processing_config.num_segments + 1)
        else:
            segment_length = self.sweeps_per_frame // processing_config.num_segments

        fft_length = segment_length * processing_config.fft_oversampling_factor
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
