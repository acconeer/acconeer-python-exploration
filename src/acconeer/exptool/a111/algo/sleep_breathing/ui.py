# Copyright (c) Acconeer AB, 2022
# All rights reserved

import numpy as np

import pyqtgraph as pg

import acconeer.exptool as et


class PGUpdater:
    def __init__(self, sensor_config, processing_config, session_info):
        self.config = sensor_config

    def setup(self, win):
        win.resize(800, 600)
        win.setWindowTitle("Acconeer sleep breathing estimation example")

        phi_title = "Breathing motion (detection range: {} m to {} m)".format(
            *self.config.range_interval
        )
        self.phi_plot = win.addPlot(title=phi_title)
        self.phi_plot.setMenuEnabled(False)
        self.phi_plot.setMouseEnabled(x=False, y=False)
        self.phi_plot.hideButtons()
        self.phi_plot.showGrid(x=True, y=True)
        self.phi_plot.setLabel("left", "Amplitude")
        self.phi_plot.setLabel("bottom", "Samples")
        self.phi_plot.addLegend()
        self.filt_phi_curve = self.phi_plot.plot(
            pen=et.utils.pg_pen_cycler(0),
            name="Filtered",
        )
        self.raw_phi_curve = self.phi_plot.plot(
            pen=et.utils.pg_pen_cycler(1),
            name="Raw",
        )

        win.nextRow()

        self.spect_plot = win.addPlot(title="Power spectrum")
        self.spect_plot.setMenuEnabled(False)
        self.spect_plot.setMouseEnabled(x=False, y=False)
        self.spect_plot.hideButtons()
        self.spect_plot.showGrid(x=True, y=True)
        self.spect_plot.setLabel("left", "Power")
        self.spect_plot.setLabel("bottom", "Frequency (Hz)")
        self.spect_curve = self.spect_plot.plot(pen=et.utils.pg_pen_cycler(1))
        self.spect_smax = et.utils.SmoothMax(self.config.update_rate / 15)
        self.spect_dft_inf_line = pg.InfiniteLine(pen=et.utils.pg_pen_cycler(1, "--"))
        self.spect_plot.addItem(self.spect_dft_inf_line)
        self.spect_est_inf_line = pg.InfiniteLine(pen=et.utils.pg_pen_cycler(0, "--"))
        self.spect_plot.addItem(self.spect_est_inf_line)
        self.spect_plot.setXRange(0, 1)
        self.spect_plot.setYRange(0, 1)
        self.spect_text_item = pg.TextItem("Initiating...", anchor=(0.5, 0.5), color="k")
        self.spect_text_item.setPos(0.5, 0.5)
        self.spect_plot.addItem(self.spect_text_item)

        win.nextRow()
        self.fest_plot = win.addPlot(title="Breathing estimation history")
        self.fest_plot.setMenuEnabled(False)
        self.fest_plot.setMouseEnabled(x=False, y=False)
        self.fest_plot.hideButtons()
        self.fest_plot.showGrid(x=True, y=True)
        self.fest_plot.setLabel("left", "Frequency (Hz)")
        self.fest_plot.setLabel("bottom", "Samples")
        self.fest_plot.addLegend()
        self.fest_curve = self.fest_plot.plot(
            pen=et.utils.pg_pen_cycler(0),
            name="Breathing est.",
        )
        self.fest_dft_curve = self.fest_plot.plot(
            pen=et.utils.pg_pen_cycler(1),
            name="DFT est.",
        )
        self.fest_plot.setXRange(0, 1)
        self.fest_plot.setYRange(0, 0.5)
        self.fest_text_item = pg.TextItem(anchor=(0, 0), color="k")
        self.fest_text_item.setPos(0, 0.5)
        self.fest_plot.addItem(self.fest_text_item)

    def update(self, data):
        self.filt_phi_curve.setData(np.squeeze(data["phi_filt"]))
        self.raw_phi_curve.setData(np.squeeze(data["phi_raw"]))

        if data["init_progress"] is not None:
            self.spect_text_item.setText("Initiating: {} %".format(data["init_progress"]))
        else:
            snr = data["snr"]
            if snr == 0:
                s = "SNR: N/A | {:.0f} dB".format(10 * np.log10(data["lambda_p"]))
            else:
                fmt = "SNR: {:.0f} | {:.0f} dB"
                s = fmt.format(10 * np.log10(snr), 10 * np.log10(data["lambda_p"]))
            self.spect_text_item.setText(s)
            self.spect_text_item.setAnchor((0, 1))
            self.spect_text_item.setPos(0, 0)

            f_est = data["f_est"]
            if f_est > 0:
                s = "Latest frequency estimate: {:.2f} Hz | {:.0f} BPM".format(f_est, f_est * 60)
                self.fest_text_item.setText(s)

            self.fest_plot.enableAutoRange(x=True)
            self.spect_curve.setData(data["x_dft"], data["power_spectrum"])
            self.spect_dft_inf_line.setValue(data["f_dft_est"])
            self.spect_est_inf_line.setValue(data["f_est"])
            self.spect_plot.setYRange(0, self.spect_smax.update(data["power_spectrum"]))
            self.fest_curve.setData(np.squeeze(data["f_est_hist"]))
            self.fest_dft_curve.setData(np.squeeze(data["f_dft_est_hist"]))
