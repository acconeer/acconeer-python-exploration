# Copyright (c) Acconeer AB, 2024-2026
# All rights reserved

from __future__ import annotations

import argparse
import os
import time

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


""" Heatmap Config to use for heatmap generation."""
HEATMAP_CONFIG = HeatmapConfig(
    antenna_array=a2.AntennaArray.AP212,
    heatmap_mode=HeatmapConfig.HeatmapMode.MOVEMENT,
    covariance_matrix_time_constant_s=0.15,
    high_pass_filter_time_constant_s=1.0,
    az_angle_range=[-60.0, 60.0],
    el_angle_range=[0.0, 0.0],
    num_az_angles=25,
    num_el_angles=1,
)

DEGREE_SYMBOL = "\u00b0"
BASE_STEP_LENGTH = 2.5e-3
SKIN = os.environ.get("ACC_SKIN", "none").lower()
TEXT_COLOR = "white" if SKIN == "tron" else "black"


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
        "--input-file",
        required=True,
        help="path to h5 record with data to visualize with heatmap processor.",
    )

    args = parser.parse_args()

    input_file = args.input_file

    # Load the recorded data
    record = a2.open_record(input_file)

    # Figure out update rate
    ticks_per_second = record.server_info.ticks_per_second
    session_index = 0  # Can be different but is usually zero
    tick_period = record.session(session_index).tick_period
    if tick_period > 0.0:
        update_rate = ticks_per_second / tick_period
    else:
        update_rate = 10  # Default value, manually adjust here if required.

    session_config = record.session_config
    subsweep_config = (
        session_config.sensor_config.subsweep
    )  # Assume that we only have a single subsweep.
    processor = HeatmapProcessor(
        subsweep_config=subsweep_config,
        heatmap_config=HEATMAP_CONFIG,
        update_rate=update_rate,
    )

    # Set up the heatmap plot
    pg_updater = PGUpdater(session_config, HEATMAP_CONFIG)
    pg_process = et.PGProcess(pg_updater)
    pg_process.start()

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    while not interrupt_handler.got_signal:
        # Go through all of the recorded data
        for result in record.results:
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
            time.sleep(1.0 / update_rate)

    print("Disconnecting...")
    pg_process.close()


if __name__ == "__main__":
    main()
