# Copyright (c) Acconeer AB, 2023
# All rights reserved

from __future__ import annotations

import numpy as np

# Added here to force pyqtgraph to choose PySide
import PySide6  # noqa: F401

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121.algo.bilateration import Processor, ProcessorConfig
from acconeer.exptool.a121.algo.distance import Detector, DetectorConfig, ThresholdMethod


_SENSOR_IDS = [2, 3]


def main():
    args = a121.ExampleArgumentParser().parse_args()
    et.utils.config_logging(args)

    client = a121.Client.open(**a121.get_client_args(args))

    detector_config = DetectorConfig(
        start_m=0.25,
        end_m=1.0,
        signal_quality=25.0,
        max_profile=a121.Profile.PROFILE_1,
        max_step_length=2,
        threshold_method=ThresholdMethod.CFAR,
    )

    detector = Detector(client=client, sensor_ids=_SENSOR_IDS, detector_config=detector_config)

    session_config = detector.session_config

    processor_config = ProcessorConfig()

    processor = Processor(
        session_config=session_config, processor_config=processor_config, sensor_ids=_SENSOR_IDS
    )

    detector.calibrate_detector()

    detector.start()

    pg_updater = PlotPlugin(detector_config=detector_config, bilateration_config=processor_config)
    pg_process = et.PGProcess(pg_updater)
    pg_process.start()

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    while not interrupt_handler.got_signal:
        detector_result = detector.get_next()
        processor_result = processor.process(detector_result)

        try:
            pg_process.put_data(
                {"detector_result": detector_result, "processor_result": processor_result}
            )
        except et.PGProccessDiedException:
            break

    detector.stop()

    print("Disconnecting...")
    client.close()


class PlotPlugin:

    _NUM_POINTS_ON_CIRCLE = 100

    def __init__(
        self,
        bilateration_config: ProcessorConfig,
        detector_config: DetectorConfig,
    ) -> None:

        self.num_curves = 5
        self.detector_config = detector_config
        self.sensor_half_spacing_m = bilateration_config.sensor_spacing_m / 2

    def setup(self, win):

        # Define sweep plot.
        self.sweep_plot = win.addPlot(row=0, col=0)
        self.sweep_plot.setMenuEnabled(False)
        self.sweep_plot.showGrid(x=True, y=True)
        self.sweep_plot.addLegend()
        self.sweep_plot.setLabel("left", "Amplitude")
        self.sweep_plot.setLabel("bottom", "Distance (m)")
        self.sweep_plot.addItem(pg.PlotDataItem())

        pen_sweep_0 = et.utils.pg_pen_cycler(0)
        pen_sweep_1 = et.utils.pg_pen_cycler(1)

        # Add sweep curves for the two sensors.
        feat_kw_1 = dict(pen=pen_sweep_0)
        feat_kw_2 = dict(pen=pen_sweep_1)
        self.sweep_curves_1 = [self.sweep_plot.plot(**feat_kw_1) for _ in range(self.num_curves)]
        self.sweep_curves_2 = [self.sweep_plot.plot(**feat_kw_2) for _ in range(self.num_curves)]

        pen_sweep_0 = et.utils.pg_pen_cycler(0, "--")
        pen_sweep_1 = et.utils.pg_pen_cycler(1, "--")

        # Add threshold curves for the two sensors.
        feat_kw_1 = dict(pen=pen_sweep_0)
        feat_kw_2 = dict(pen=pen_sweep_1)
        self.threshold_curves_1 = [
            self.sweep_plot.plot(**feat_kw_1) for _ in range(self.num_curves)
        ]
        self.threshold_curves_2 = [
            self.sweep_plot.plot(**feat_kw_2) for _ in range(self.num_curves)
        ]

        # Add legends.
        sweep_plot_legend = pg.LegendItem(offset=(0.0, 0.5))
        sweep_plot_legend.setParentItem(self.sweep_plot)
        sweep_plot_legend.addItem(self.sweep_curves_1[0], "Sweep - Left sensor")
        sweep_plot_legend.addItem(self.threshold_curves_1[0], "Threshold - Left sensor")
        sweep_plot_legend.addItem(self.sweep_curves_2[0], "Sweep - Right sensor")
        sweep_plot_legend.addItem(self.threshold_curves_2[0], "Threshold - Right sensor")

        self.sweep_smooth_max = et.utils.SmoothMax()

        # Define obstacle plot.
        self.obstacle_location_plot = win.addPlot(row=1, col=0)
        self.obstacle_location_plot.setMenuEnabled(False)
        self.obstacle_location_plot.setAspectLocked()
        self.obstacle_location_plot.showGrid(x=True, y=True)
        self.obstacle_location_plot.addLegend()
        self.obstacle_location_plot.setLabel("left", "Y (m)")
        self.obstacle_location_plot.setLabel("bottom", "X (m)")
        self.obstacle_location_plot.addItem(pg.PlotDataItem())
        self.obstacle_location_plot.setXRange(
            -self.detector_config.end_m, self.detector_config.end_m
        )
        self.obstacle_location_plot.setYRange(0.0, self.detector_config.end_m)

        pen_sweep_0 = et.utils.pg_pen_cycler(0)
        brush_sweep_0 = et.utils.pg_brush_cycler(0)
        symbol_kw = dict(symbol="o", symbolSize=10, symbolBrush=brush_sweep_0, symbolPen=None)
        feat_kw = dict(pen=None, **symbol_kw)
        self.obstacle_location_curve = self.obstacle_location_plot.plot(**feat_kw)
        feat_kw = dict(pen=pen_sweep_0)
        self.obstacle_location_half_curve = [
            self.obstacle_location_plot.plot(**feat_kw) for _ in range(Processor._MAX_NUM_OBJECTS)
        ]

    def update(self, data) -> None:

        detector_result = data["detector_result"]
        processor_result = data["processor_result"]

        # Plot sweep data from both distance detectors.
        max_val = 0.0
        for distance_detector_result, sweep_curves, threshold_curves in zip(
            detector_result.values(),
            [self.sweep_curves_1, self.sweep_curves_2],
            [self.threshold_curves_1, self.threshold_curves_2],
        ):
            for idx, distance_processor_result in enumerate(
                distance_detector_result.processor_results
            ):

                abs_sweep = distance_processor_result.extra_result.abs_sweep
                threshold = distance_processor_result.extra_result.used_threshold
                distances_m = distance_processor_result.extra_result.distances_m

                assert abs_sweep is not None
                assert threshold is not None
                assert distances_m is not None

                sweep_curves[idx].setData(distances_m, abs_sweep)
                threshold_curves[idx].setData(distances_m, threshold)

                if max_val < np.max(abs_sweep):
                    max_val = float(np.max(abs_sweep))

                if max_val < np.max(threshold):
                    max_val = float(np.max(threshold))

        if max_val != 0.0:
            self.sweep_plot.setYRange(0.0, self.sweep_smooth_max.update(max_val))

        # Plot result from bilateration processor.
        # Start with the points.
        points = processor_result.points
        xs = [point.x_coord for point in points]
        ys = [point.y_coord for point in points]
        self.obstacle_location_curve.setData(xs, ys)

        # Plot objects without counter part.
        objects_without_counterpart = processor_result.objects_without_counterpart
        for i, o in enumerate(objects_without_counterpart):
            x = np.cos(np.linspace(0, np.pi, self._NUM_POINTS_ON_CIRCLE)) * o.distance
            y = np.sin(np.linspace(0, np.pi, self._NUM_POINTS_ON_CIRCLE)) * o.distance

            # Offset circle to center around the sensor that detected the object.
            if o.sensor_position == Processor._SENSOR_POSITION_LEFT:
                x -= self.sensor_half_spacing_m
            elif o.sensor_position == Processor._SENSOR_POSITION_RIGHT:
                x += self.sensor_half_spacing_m
            else:
                raise ValueError("Invalid sensor position.")

            self.obstacle_location_half_curve[i].setData(x, y)

        # Remove curves that does not have an object to visualize.
        for i in range(len(objects_without_counterpart), Processor._MAX_NUM_OBJECTS):
            self.obstacle_location_half_curve[i].setData([], [])


if __name__ == "__main__":
    main()
