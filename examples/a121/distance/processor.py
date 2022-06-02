from __future__ import annotations

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121.algo.distance import (
    DistanceProcessor,
    DistanceProcessorConfig,
    ProcessorMode,
    ThresholdMethod,
)


def main():
    args = a121.ExampleArgumentParser().parse_args()
    et.utils.config_logging(args)

    client = a121.Client(**a121.get_client_args(args))
    client.connect()

    sensor_config = a121.SensorConfig(
        subsweeps=[
            a121.SubsweepConfig(
                start_point=50,
                step_length=4,
                num_points=25,
                profile=a121.Profile.PROFILE_1,
                hwaas=10,
                phase_enhancement=True,
            ),
            a121.SubsweepConfig(
                start_point=150,
                step_length=4,
                num_points=25,
                profile=a121.Profile.PROFILE_1,
                hwaas=20,
                phase_enhancement=True,
            ),
        ],
        sweeps_per_frame=5,
    )

    metadata = client.setup_session(sensor_config)

    config = DistanceProcessorConfig(
        processor_mode=ProcessorMode.DISTANCE_ESTIMATION, threshold_method=ThresholdMethod.RECORDED
    )
    processor = DistanceProcessor(
        sensor_config=sensor_config,
        metadata=metadata,
        processor_config=config,
    )

    pg_updater = PGUpdater(None)
    pg_process = et.PGProcess(pg_updater)
    pg_process.start()

    client.start_session()

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    while not interrupt_handler.got_signal:
        extended_result = client.get_next()
        processed_data = processor.process(extended_result)
        try:
            pg_process.put_data(processed_data)
        except et.PGProccessDiedException:
            break

    print("Disconnecting...")
    pg_process.close()
    client.disconnect()


class PGUpdater:
    def __init__(self, processing_config):
        self.processing_config = processing_config

    def setup(self, win):
        self.subsweep_plot = win.addPlot(row=0, col=0)
        self.subsweep_plot.setMenuEnabled(False)
        self.subsweep_plot.showGrid(x=True, y=True)
        self.subsweep_plot.addLegend()
        self.subsweep_plot.setLabel("left", "Amplitude")
        self.subsweep_plot.addItem(pg.PlotDataItem())
        pen = et.utils.pg_pen_cycler(0)
        brush = et.utils.pg_brush_cycler(0)
        symbol_kw = dict(symbol="o", symbolSize=1, symbolBrush=brush, symbolPen="k")
        feat_kw = dict(pen=pen, **symbol_kw)
        self.subsweep_curve = self.subsweep_plot.plot(**feat_kw, name="Sweep")
        self.smooth_max = et.utils.SmoothMax()

    def update(self, d):
        self.subsweep_curve.setData(d.extra.abs_sweep)


if __name__ == "__main__":
    main()
