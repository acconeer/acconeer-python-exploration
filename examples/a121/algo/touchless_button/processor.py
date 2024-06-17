# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved

from __future__ import annotations

import numpy as np

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121.algo.touchless_button import (
    MeasurementType,
    Processor,
    ProcessorConfig,
    ProcessorResult,
    get_close_sensor_config,
)


def main():
    args = a121.ExampleArgumentParser().parse_args()
    et.utils.config_logging(args)

    client = a121.Client.open(**a121.get_client_args(args))

    processor_config = ProcessorConfig()

    sensor_config = get_close_sensor_config()

    metadata = client.setup_session(sensor_config)
    client.start_session()

    processor = Processor(
        sensor_config=sensor_config,
        metadata=metadata,
        processor_config=processor_config,
    )

    pg_updater = PGUpdater(sensor_config=sensor_config, processor_config=processor_config)
    pg_process = et.PGProcess(pg_updater)
    pg_process.start()

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    while not interrupt_handler.got_signal:
        result = client.get_next()
        processor_result = processor.process(result)
        try:
            pg_process.put_data(processor_result)
        except et.PGProccessDiedException:
            break

    print("Disconnecting...")
    pg_process.close()
    client.stop_session()
    client.close()


class PGUpdater:
    def __init__(self, sensor_config, processor_config):
        self.detection_history = np.full((2, 100), np.nan)
        self.sensor_config = sensor_config
        self.processor_config = processor_config

    def setup(self, win):
        self.detection_history_plot = self._create_detection_plot(win)

        self.detection_history_curve_close = self.detection_history_plot.plot(
            pen=et.utils.pg_pen_cycler(1, width=5)
        )
        self.detection_history_curve_far = self.detection_history_plot.plot(
            pen=et.utils.pg_pen_cycler(0, width=5)
        )

        close_html = (
            '<div style="text-align: center">'
            '<span style="color: #FFFFFF;font-size:15pt;">'
            "{}</span></div>".format("Close detection")
        )
        far_html = (
            '<div style="text-align: center">'
            '<span style="color: #FFFFFF;font-size:15pt;">'
            "{}</span></div>".format("Far detection")
        )
        self.close_text_item = pg.TextItem(
            html=close_html,
            fill=pg.mkColor(0xFF, 0x7F, 0x0E),
            anchor=(0.5, 0),
        )
        self.far_text_item = pg.TextItem(
            html=far_html,
            fill=pg.mkColor(0x1F, 0x77, 0xB4),
            anchor=(0.5, 0),
        )
        pos_left = (100 / 3, 1.8)
        pos_right = (2 * 100 / 3, 1.8)
        self.close_text_item.setPos(*pos_left)
        self.far_text_item.setPos(*pos_right)
        self.detection_history_plot.addItem(self.close_text_item)
        self.detection_history_plot.addItem(self.far_text_item)
        self.close_text_item.hide()
        self.far_text_item.hide()

        self.detection_history = np.full((2, 100), np.nan)

        self.score_history_plot = self._create_score_plot(win)
        score_plot_legend = self.score_history_plot.legend
        self.score_smooth_max = et.utils.SmoothMax()

        self.threshold_history_curve_close = self.score_history_plot.plot(
            pen=et.utils.pg_pen_cycler(1, width=2.5, style="--"),
        )
        self.threshold_history_curve_far = self.score_history_plot.plot(
            pen=et.utils.pg_pen_cycler(0, width=2.5, style="--"),
        )

        self.threshold_history = np.full((2, 100), np.nan)

        cycle_index = 2  # To not have same colors as thresholds
        if self.processor_config.measurement_type == MeasurementType.CLOSE_RANGE:
            measurement_type = "Close"
            score_plot_legend.addItem(self.threshold_history_curve_close, "Close range threshold")
        elif self.processor_config.measurement_type == MeasurementType.FAR_RANGE:
            measurement_type = "Far"
            score_plot_legend.addItem(self.threshold_history_curve_far, "Far range threshold")

        if self.processor_config.measurement_type != MeasurementType.CLOSE_AND_FAR_RANGE:
            score_history = np.full((self.sensor_config.subsweep.num_points, 100), np.nan)
            score_history_curves = np.empty(
                (self.sensor_config.subsweep.num_points,), dtype=object
            )
            for i in range(self.sensor_config.subsweep.num_points):
                score_history_curves[i] = pg.ScatterPlotItem(
                    brush=et.utils.pg_brush_cycler(cycle_index),
                    name=f"{measurement_type} range, point {i}",
                )
                self.score_history_plot.addItem(score_history_curves[i])
                cycle_index += 1

            if self.processor_config.measurement_type == MeasurementType.CLOSE_RANGE:
                self.score_history_close = score_history
                self.score_history_curves_close = score_history_curves
                self.score_history_far = None
                self.score_history_curves_far = None
            elif self.processor_config.measurement_type == MeasurementType.FAR_RANGE:
                self.score_history_close = None
                self.score_history_curves_close = None
                self.score_history_far = score_history
                self.score_history_curves_far = score_history_curves

        elif self.processor_config.measurement_type == MeasurementType.CLOSE_AND_FAR_RANGE:
            score_plot_legend.addItem(self.threshold_history_curve_close, "Close range threshold")
            score_plot_legend.addItem(self.threshold_history_curve_far, "Far range threshold")
            self.score_history_close = np.full(
                (self.sensor_config.subsweeps[0].num_points, 100), np.nan
            )
            self.score_history_far = np.full(
                (self.sensor_config.subsweeps[1].num_points, 100), np.nan
            )
            self.score_history_curves_close = np.empty(
                (self.sensor_config.subsweeps[0].num_points,), dtype=object
            )
            self.score_history_curves_far = np.empty(
                (self.sensor_config.subsweeps[1].num_points,), dtype=object
            )

            range_labels = ["Close", "Far"]
            for n, subsweep in enumerate(self.sensor_config.subsweeps):
                measurement_type = range_labels[n]
                score_history_curve_list = [
                    self.score_history_curves_close,
                    self.score_history_curves_far,
                ]
                for i in range(subsweep.num_points):
                    score_history_curve_list[n][i] = pg.ScatterPlotItem(
                        brush=et.utils.pg_brush_cycler(cycle_index),
                        name=f"{measurement_type} range, point {i}",
                    )
                    self.score_history_plot.addItem(score_history_curve_list[n][i])
                    cycle_index += 1
            self.score_history_curves_close = score_history_curve_list[0]
            self.score_history_curves_far = score_history_curve_list[1]

    def update(self, processor_result: ProcessorResult):
        def is_none_or_detection(x):
            return x.detection if x is not None else None

        detection = np.array(
            [
                is_none_or_detection(processor_result.close),
                is_none_or_detection(processor_result.far),
            ]
        )
        self.detection_history = np.roll(self.detection_history, -1, axis=1)
        self.detection_history[:, -1] = detection

        self.detection_history_curve_close.setData(self.detection_history[0])
        self.detection_history_curve_far.setData(self.detection_history[1])

        if processor_result.close is not None:
            if processor_result.close.detection:
                self.close_text_item.show()
            else:
                self.close_text_item.hide()

        if processor_result.far is not None:
            if processor_result.far.detection:
                self.far_text_item.show()
            else:
                self.far_text_item.hide()

        max_val = 0.0

        def is_none_or_threshold(x):
            return x.threshold if x is not None else None

        threshold = np.array(
            [
                is_none_or_threshold(processor_result.close),
                is_none_or_threshold(processor_result.far),
            ]
        )
        if np.nanmax(np.array(threshold, dtype=float)) > max_val:
            max_val = np.nanmax(np.array(threshold, dtype=float))
        self.threshold_history = np.roll(self.threshold_history, -1, axis=1)
        self.threshold_history[:, -1] = threshold

        self.threshold_history_curve_close.setData(self.threshold_history[0])
        self.threshold_history_curve_far.setData(self.threshold_history[1])

        if self.score_history_close is not None:
            self.score_history_close = np.roll(self.score_history_close, -1, axis=1)
            assert processor_result.close is not None
            # Plot the second highest score
            self.score_history_close[:, -1] = np.sort(processor_result.close.score, axis=0)[-2, :]

            assert self.score_history_curves_close is not None
            for i, curve in enumerate(self.score_history_curves_close):
                # Assign x-values so that setData() doesn't give error when y-values are NaN
                curve.setData(np.arange(0, 100), self.score_history_close[i, :].flatten())

            if np.max(processor_result.close.score) > max_val:
                max_val = np.max(processor_result.close.score)

        if self.score_history_far is not None:
            self.score_history_far = np.roll(self.score_history_far, -1, axis=1)
            assert processor_result.far is not None
            # Plot the second highest score
            self.score_history_far[:, -1] = np.sort(processor_result.far.score, axis=0)[-2, :]

            assert self.score_history_curves_far is not None
            for i, curve in enumerate(self.score_history_curves_far):
                # Assign x-values so that setData() doesn't give error when y-values are NaN
                curve.setData(np.arange(0, 100), self.score_history_far[i, :].flatten())

            if np.max(processor_result.far.score) > max_val:
                max_val = np.max(processor_result.far.score)

        if max_val != 0.0:
            self.score_history_plot.setYRange(0.0, self.score_smooth_max.update(max_val))

    @staticmethod
    def _create_detection_plot(parent: pg.GraphicsLayout) -> pg.PlotItem:
        detection_history_plot = parent.addPlot(row=0, col=0)
        detection_history_plot.setTitle("Detection")
        detection_history_plot.setLabel(axis="bottom", text="Frames")
        detection_history_plot.setMenuEnabled(False)
        detection_history_plot.setMouseEnabled(x=False, y=False)
        detection_history_plot.hideButtons()
        detection_history_plot.showGrid(x=True, y=True, alpha=0.5)
        detection_history_plot.setYRange(-0.1, 1.8)
        return detection_history_plot

    @staticmethod
    def _create_score_plot(parent: pg.GraphicsLayout) -> pg.PlotItem:
        score_history_plot = parent.addPlot(row=1, col=0)
        score_history_plot.setTitle("Detection score")
        score_history_plot.setLabel(axis="bottom", text="Frames")
        score_history_plot.addLegend()
        score_history_plot.setMenuEnabled(False)
        score_history_plot.setMouseEnabled(x=False, y=False)
        score_history_plot.hideButtons()
        score_history_plot.showGrid(x=True, y=True, alpha=0.5)
        return score_history_plot


if __name__ == "__main__":
    main()
