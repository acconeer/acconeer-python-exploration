# Copyright (c) Acconeer AB, 2023
# All rights reserved

from __future__ import annotations

import numpy as np

# Added here to force pyqtgraph to choose PySide
# import PySide6  # noqa: F401
# from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget
from PySide6.QtGui import QTransform

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121.algo.obstacle import Detector, DetectorConfig, DetectorResult


SENSOR_IDS = [2, 3]


def main():
    args = a121.ExampleArgumentParser().parse_args()
    et.utils.config_logging(args)

    client = a121.Client.open(**a121.get_client_args(args))

    # Creating a list of subsweep configurations.
    subsweep_configurations = [
        a121.SubsweepConfig(
            start_point=24,  # ~6 cm
            num_points=96,
            step_length=1,
            profile=a121.Profile.PROFILE_1,
            hwaas=4,
        ),
        a121.SubsweepConfig(
            start_point=96,  # ~24 cm
            num_points=48,
            step_length=4,
            profile=a121.Profile.PROFILE_3,
            hwaas=16,
        ),
        a121.SubsweepConfig(
            start_point=300,  # ~75 cm
            num_points=48,
            step_length=4,
            profile=a121.Profile.PROFILE_3,
            hwaas=2,
        ),
    ]

    # Configure the detector using multiple subsweeps
    detector_config = DetectorConfig(
        enable_bilateration=(len(SENSOR_IDS) == 2),
        bilateration_sensor_spacing_m=0.1,
        num_mean_threshold=1.5,
        num_std_threshold=4,
        subsweep_configurations=subsweep_configurations,
    )

    detector = Detector(client=client, sensor_ids=SENSOR_IDS, detector_config=detector_config)

    detector.calibrate_detector()
    detector.start()

    pg_updater = PGUpdater(
        num_sensors=len(SENSOR_IDS),
        num_subsweeps=len(subsweep_configurations),
        enable_bilateration=detector_config.enable_bilateration,
    )

    pg_process = et.PGProcess(pg_updater)
    pg_process.start()

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    while not interrupt_handler.got_signal:
        # v_current = get_speed_from_some_Robot_API(), e.g ROS?
        # detector.update_robot_speed(v_current)

        detector_result = detector.get_next()

        try:
            pg_process.put_data(detector_result)
        except et.PGProccessDiedException:
            break

    detector.stop()

    print("Disconnecting...")
    client.close()


PLOT_HISTORY_FRAMES = 50
PLOT_THRESHOLDS = True


class PGUpdater:
    def __init__(self, num_sensors, num_subsweeps, enable_bilateration):
        self.num_sensors = num_sensors
        self.num_subsweeps = num_subsweeps
        self.enable_bilateration = enable_bilateration
        self.obst_vel_ys = num_sensors * [np.nan * np.ones(PLOT_HISTORY_FRAMES)]
        self.obst_dist_ys = num_sensors * [np.nan * np.ones(PLOT_HISTORY_FRAMES)]
        self.obst_bil_ys = np.nan * np.ones(PLOT_HISTORY_FRAMES)
        self.hist_x = np.linspace(-100, 0, PLOT_HISTORY_FRAMES)

    def setup(self, win: pg.GraphicsLayout):

        self.fftmap_plots: list[pg.PlotItem] = []
        self.fftmap_images: list[pg.ImageItem] = []
        self.range_hist_curves: list[pg.PlotDataItem] = []
        self.angle_hist_curves: list[pg.PlotDataItem] = []

        if PLOT_THRESHOLDS:
            self.bin0_curves: list[pg.PlotDataItem] = []
            self.bin0_threshold_curves: list[pg.PlotDataItem] = []
            self.other_bins_curves: list[pg.PlotDataItem] = []
            self.other_bins_threshold_curves: list[pg.PlotDataItem] = []

        row_offset = 2 if PLOT_THRESHOLDS else 0

        for i_s in range(self.num_sensors):
            for i_ss in range(self.num_subsweeps):
                col = i_s * self.num_subsweeps + i_ss
                p = win.addPlot(
                    row=0, col=col, title=f"FFT Map, sensor {SENSOR_IDS[i_s]}, subsweep {i_ss}"
                )
                im = pg.ImageItem(autoDownsample=True)
                im.setLookupTable(et.utils.pg_mpl_cmap("viridis"))
                self.fftmap_images.append(im)

                p.setLabel("bottom", "Distance (cm)")
                p.setLabel("left", "Velocity (cm/s)")
                p.addItem(im)

                self.fftmap_plots.append(p)

            if PLOT_THRESHOLDS:

                self.bin0 = pg.PlotItem(title="Zeroth velocity/angle bin")
                self.bin0.showGrid(x=True, y=True)
                self.bin0.setLabel("bottom", "Range (cm)")
                self.bin0.setLabel("left", "Amplitude")
                self.bin0.addLegend()

                pen = et.utils.pg_pen_cycler(0)
                brush = et.utils.pg_brush_cycler(0)
                symbol_kw = dict(symbol="o", symbolSize=1, symbolBrush=brush, symbolPen="k")
                feat_kw = dict(pen=pen, **symbol_kw)
                self.bin0_curves += [self.bin0.plot(**feat_kw) for _ in range(self.num_subsweeps)]

                pen = et.utils.pg_pen_cycler(1)
                brush = et.utils.pg_brush_cycler(1)
                symbol_kw = dict(symbol="o", symbolSize=1, symbolBrush=brush, symbolPen="k")
                feat_kw = dict(pen=pen, **symbol_kw)
                self.bin0_threshold_curves += [
                    self.bin0.plot(**feat_kw) for _ in range(self.num_subsweeps)
                ]

                bin0_plot_legend = pg.LegendItem(offset=(0.0, 0.5))
                bin0_plot_legend.setParentItem(self.bin0)
                bin0_plot_legend.addItem(self.bin0_curves[0], "Sweep")
                bin0_plot_legend.addItem(self.bin0_threshold_curves[0], "Threshold")

                sublayout = win.addLayout(
                    row=1,
                    col=i_s * self.num_subsweeps,
                    colspan=self.num_subsweeps,
                )
                sublayout.layout.setColumnStretchFactor(0, self.num_subsweeps)
                sublayout.addItem(self.bin0, row=0, col=0)

                self.other_bins = pg.PlotItem(title="Other velocity/angle bins")
                self.other_bins.showGrid(x=True, y=True)
                self.other_bins.setLabel("bottom", "Range (cm)")
                self.other_bins.setLabel("left", "Amplitude")
                self.other_bins.addLegend()

                pen = et.utils.pg_pen_cycler(0)
                brush = et.utils.pg_brush_cycler(0)
                symbol_kw = dict(symbol="o", symbolSize=1, symbolBrush=brush, symbolPen="k")
                feat_kw = dict(pen=pen, **symbol_kw)
                self.other_bins_curves += [
                    self.other_bins.plot(**feat_kw) for _ in range(self.num_subsweeps)
                ]

                pen = et.utils.pg_pen_cycler(1)
                brush = et.utils.pg_brush_cycler(1)
                symbol_kw = dict(symbol="o", symbolSize=1, symbolBrush=brush, symbolPen="k")
                feat_kw = dict(pen=pen, **symbol_kw)
                self.other_bins_threshold_curves += [
                    self.other_bins.plot(**feat_kw) for _ in range(self.num_subsweeps)
                ]

                other_bins_plot_legend = pg.LegendItem(offset=(0.0, 0.5))
                other_bins_plot_legend.setParentItem(self.other_bins)
                other_bins_plot_legend.addItem(self.other_bins_curves[0], "Max Sweep")
                other_bins_plot_legend.addItem(self.other_bins_threshold_curves[0], "Threshold")

                sublayout = win.addLayout(
                    row=2,
                    col=i_s * self.num_subsweeps,
                    colspan=self.num_subsweeps,
                )
                sublayout.layout.setColumnStretchFactor(0, self.num_subsweeps)
                sublayout.addItem(self.other_bins, row=0, col=0)

            self.angle_hist = pg.PlotItem(title="Angle/velocity history")
            self.angle_hist.showGrid(x=True, y=True)
            self.angle_hist.setLabel("bottom", "Time (frames)")
            self.angle_hist.setLabel("left", "velocity (cm/s)")
            self.angle_hist.setXRange(-100, 0)
            self.angle_hist.addLegend()
            self.angle_hist_curves.append(self.angle_hist.plot(symbolSize=5, symbol="o"))

            sublayout = win.addLayout(
                row=1 + row_offset,
                col=i_s * self.num_subsweeps,
                colspan=self.num_subsweeps,
            )

            sublayout.layout.setColumnStretchFactor(0, self.num_subsweeps)
            sublayout.addItem(self.angle_hist, row=0, col=0)

            self.range_hist = pg.PlotItem(title="Range history")
            self.range_hist.showGrid(x=True, y=True)
            self.range_hist.setLabel("bottom", "Time (frames)")
            self.range_hist.setLabel("left", "Range (cm)")
            self.range_hist.setXRange(-100, 0)
            self.range_hist.addLegend()
            self.range_hist_curves.append(self.range_hist.plot(symbolSize=5, symbol="o"))

            sublayout = win.addLayout(
                row=2 + row_offset,
                col=i_s * self.num_subsweeps,
                colspan=self.num_subsweeps,
            )

            sublayout.layout.setColumnStretchFactor(0, self.num_subsweeps)
            sublayout.addItem(self.range_hist, row=0, col=0)

        if self.enable_bilateration:

            self.bil_hist_plot = pg.PlotItem(title="Bilateration history")

            self.bil_hist_plot.showGrid(x=True, y=True)
            self.bil_hist_plot.setLabel("bottom", "Time (frames)")
            self.bil_hist_plot.setLabel("left", "Bilateration angle (deg)")
            self.bil_hist_plot.setXRange(-100, 0)
            self.bil_hist_plot.setYRange(-90, 90)
            self.bil_hist_plot.addLegend()

            self.bil_hist_curve = self.bil_hist_plot.plot(pen=et.utils.pg_pen_cycler(1))

            sublayout = win.addLayout(row=3 + row_offset, col=0, colspan=2 * self.num_subsweeps)
            sublayout.layout.setColumnStretchFactor(0, 2 * self.num_subsweeps)
            sublayout.addItem(self.bil_hist_plot, row=0, col=0)

    def update(self, detector_result: DetectorResult):

        for i_s in range(self.num_sensors):
            pr = detector_result.processor_results[SENSOR_IDS[i_s]]

            for i_ss in range(self.num_subsweeps):

                curve_idx = self.num_subsweeps * i_s + i_ss

                fftmap = pr.subsweeps_extra_results[i_ss].fft_map
                fftmap_threshold = pr.subsweeps_extra_results[i_ss].fft_map_threshold

                # fftmap = 10*np.log10(fftmap)  # to dB

                spf = fftmap.shape[0]
                r = 100 * pr.subsweeps_extra_results[i_ss].r

                transform = QTransform()
                transform.translate(
                    r[0], -100 * pr.extra_result.dv * spf / 2 - 0.5 * 100 * pr.extra_result.dv
                )
                transform.scale(r[1] - r[0], 100 * pr.extra_result.dv)

                self.fftmap_images[curve_idx].setTransform(transform)

                self.fftmap_images[curve_idx].updateImage(
                    np.fft.fftshift(fftmap, 0).T,
                    levels=(0, 1.05 * np.max(fftmap)),
                )

                if PLOT_THRESHOLDS:
                    bin0 = fftmap[0, :]
                    threshold_bin0 = fftmap_threshold[0, :]

                    max_other_bins = np.max(fftmap[1:, :], axis=0)
                    threshold_other_bins = fftmap_threshold[1, :]

                    self.bin0_curves[curve_idx].setData(r, bin0)
                    self.bin0_threshold_curves[curve_idx].setData(r, threshold_bin0)
                    self.other_bins_curves[curve_idx].setData(r, max_other_bins)
                    self.other_bins_threshold_curves[curve_idx].setData(r, threshold_other_bins)

            v = pr.targets[0].velocity if pr.targets else np.nan

            self.obst_vel_ys[i_s] = np.roll(self.obst_vel_ys[i_s], -1)
            self.obst_vel_ys[i_s][-1] = 100 * v  # m/s -> cm/s

            if np.isnan(self.obst_vel_ys[i_s]).all():
                self.angle_hist_curves[i_s].setVisible(False)
            else:
                self.angle_hist_curves[i_s].setVisible(True)
                self.angle_hist_curves[i_s].setData(
                    self.hist_x, self.obst_vel_ys[i_s], connect="finite"
                )

            # TODO: should be known earlier
            # r_min = min([er.r[0] for er in pr.subsweeps_extra_results])
            # r_max = min([er.r[-1] for er in pr.subsweeps_extra_results])
            # self.range_hist.setYRange(100*r_min, 100*r_max)

            r_targets = pr.targets[0].distance if pr.targets else np.nan

            self.obst_dist_ys[i_s] = np.roll(self.obst_dist_ys[i_s], -1)
            self.obst_dist_ys[i_s][-1] = 100 * r_targets  # m -> cm

            # print(f'{i_s}: r = {r_targets}, v = {v}')

            if np.isnan(self.obst_dist_ys[i_s]).all():
                self.range_hist_curves[i_s].setVisible(False)
            else:
                self.range_hist_curves[i_s].setVisible(True)
                self.range_hist_curves[i_s].setData(
                    self.hist_x, self.obst_dist_ys[i_s], connect="finite"
                )

        if self.enable_bilateration:

            beta = (
                detector_result.bilateration_result.beta_degs[0]
                if detector_result.bilateration_result.beta_degs
                else np.nan
            )

            self.obst_bil_ys = np.roll(self.obst_bil_ys, -1)
            self.obst_bil_ys[-1] = beta

            if np.isnan(self.obst_bil_ys).all():
                self.bil_hist_curve.setVisible(False)
            else:
                self.bil_hist_curve.setVisible(True)
                self.bil_hist_curve.setData(self.hist_x, self.obst_bil_ys, connect="finite")


if __name__ == "__main__":
    main()
