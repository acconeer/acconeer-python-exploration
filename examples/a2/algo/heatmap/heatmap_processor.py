# Copyright (c) Acconeer AB, 2024-2026
# All rights reserved

from __future__ import annotations

import argparse

import numpy as np

from PySide6.QtGui import QTransform

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a2
from acconeer.exptool.a2.algo.heatmap.conventional import (
    HeatmapConfig,
    HeatmapProcessor,
    ProcessorResult,
)


SENSOR_CONFIG = a2.SensorConfig.single_subsweep(
    # SensorConfig params.
    sweeps_per_frame=1,
    sweep_rate=None,
    # Subsweep params.
    start_point=60,
    num_points=34,
    step_length=12,
    hwaas_max=100,
    hwaas_min=4,
    hwaas_exponent=4,
    tx_antenna_mask=0b111,
    rx_antenna_mask=0b1111,
    profile=a2.Profile.PROFILE_1,
)

UPDATE_RATE = 20

HEATMAP_CONFIG = HeatmapConfig(
    num_az_angles=61,
    az_angle_range=(-60, 60),
    num_el_angles=1,
    el_angle_range=(0, 0),
    covariance_matrix_time_constant_s=0.20,
    high_pass_filter_time_constant_s=5.0,
    antenna_array=a2.AntennaArray.AP212,
    heatmap_mode=HeatmapConfig.HeatmapMode.MOVEMENT,  # or DISTANCE
)

DEGREE_SYMBOL = "\u00b0"
BASE_STEP_LENGTH = 2.5e-3


class PGUpdater:
    """
    Minimal version of plotting from exploration tool.
    """

    def __init__(self, session_config, heatmap_config) -> None:
        self._config: a2.SessionConfig | None = session_config
        self.heatmap_config = heatmap_config

    def setup(self, win):
        self.viridis_heatmap_image_item = pg.ImageItem()
        self.viridis_heatmap_image_item.setLookupTable(et.utils.pg_mpl_cmap("viridis"))

        self.viridis_heatmap_plot_item = win.addPlot(row=0, col=0, title="Heatmap Visualization")
        self.viridis_heatmap_plot_item.getAxis("left").setLabel("Distance", units="m")
        self.viridis_heatmap_plot_item.getAxis("bottom").setLabel("Az angle", units=DEGREE_SYMBOL)
        self.viridis_heatmap_colorbar = self.viridis_heatmap_plot_item.addColorBar(
            self.viridis_heatmap_image_item, colorMap="viridis"
        )

        self.viridis_heatmap_plot_item.clear()
        self.viridis_heatmap_plot_item.addItem(self.viridis_heatmap_image_item)
        self.viridis_heatmap_plot_smooth_max = et.utils.SmoothMax(
            self._config.update_rate, tau_decay=0.1, tau_grow=0.1
        )

        start_point = self._config.sensor_config.subsweep.start_point
        step_length = self._config.sensor_config.subsweep.step_length

        self.viridis_heatmap_image_item.setTransform(
            QTransform()
            .translate(-self.heatmap_config.az_span / 2, start_point * BASE_STEP_LENGTH)
            .scale(
                self.heatmap_config.az_span / len(self.heatmap_config.az_angles),
                step_length * BASE_STEP_LENGTH,
            )
        )

    def update(self, processor_result: ProcessorResult) -> None:
        """Plotting is achieved by repeated calls to update with new processorresults"""

        if processor_result.heatmap is None:
            return
        heatmap = processor_result.heatmap[:, 0, :]
        max_val = np.max(heatmap)

        max_heat = self.viridis_heatmap_plot_smooth_max.update(max_val)
        image = np.nan_to_num(heatmap)
        self.viridis_heatmap_colorbar.setLevels((0, max_heat))
        self.viridis_heatmap_image_item.updateImage(image, levels=(0, max_heat))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-file",
        default="data.h5",
        help="path to h5 file to store the radar data",
    )

    args = parser.parse_args()

    output_file = args.output_file

    with (
        a2.Client.open(
            # Leaving this comment as is will automatically search for an
            # EVK connected via USB. Otherwise, one of the following should be specified:
            #
            # ip_address="<ip address of host (like a RPi). E.g. 192.168.XXX.YYY>",
            # or
            # serial_port="<serial port of module. E.g. COM3 or /dev/ttyUSBx for Window/Linux>",
            # or
            # usb_device=True,
            # or
            # mock=True,
        ) as client
    ):
        processor = HeatmapProcessor(SENSOR_CONFIG.subsweep, HEATMAP_CONFIG, UPDATE_RATE)

        session_config = a2.SessionConfig([SENSOR_CONFIG], update_rate=UPDATE_RATE)
        client.setup_session(session_config)

        pg_updater = PGUpdater(session_config, HEATMAP_CONFIG)
        pg_process = et.PGProcess(pg_updater)
        pg_process.start()

        # Here we create and attach a H5Recorder to the Client.
        # The H5Recorder will sample all frames retrieved in the client.
        # Once the "with"-block have been exited, the H5Recorder will
        # wrap up and close the file.
        with a2.H5Recorder(output_file, client, mode="w"):
            client.start_session()

            interrupt_handler = et.utils.ExampleInterruptHandler()
            print("Press Ctrl-C to end session")

            while not interrupt_handler.got_signal:
                # Client will send its Results to the H5Recorder.
                result = client.get_next(format=a2.Client.ResultFormat.SOLE)

                # Post-process radar data and get the heatmap result
                processor_result = processor.process(result)

                # Make sure we have a heatmap to plot
                if processor_result.heatmap is None:
                    continue

                try:
                    # Plot the heatmap
                    pg_process.put_data(processor_result)
                except et.PGProccessDiedException:
                    break

            print("Disconnecting...")
            pg_process.close()
            client.stop_session()


if __name__ == "__main__":
    main()
