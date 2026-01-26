# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

from enum import Enum
from typing import Optional

import attrs
import numpy as np
import numpy.typing as npt

from PySide6 import QtCore
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLayout, QTextBrowser, QWidget

import pyqtgraph as pg

import acconeer.exptool as et

from ._example_app import ExampleAppResult
from ._processor import ProcessorExtraResult, ProcessorResult


class PeakListDisplayType(Enum):
    PEAK = "peak"
    RMS = "RMS"


class ReportedPeaksSortingMethod(Enum):
    """Selects the method used to sort reported peaks."""

    DISPLACEMENT = "displacement"
    """Sort peaks by displacement (largest first)."""

    FREQUENCY = "frequency"
    """Sort peaks by frequency (lowest first)."""

    VELOCITY = "velocity"
    """Sort peaks by velocity (largest first)."""

    ACCELERATION = "acceleration"
    """Sort peaks by acceleration (largest first)."""


class ReportedPeaksLimit(Enum):
    ALL = "all peaks"
    TEN = "max 10 peaks"
    ONE = "1 peak"


@attrs.frozen
class PeakData:
    displacements: npt.NDArray[np.float64] = attrs.field(factory=lambda: np.empty(0))
    frequencies: npt.NDArray[np.float64] = attrs.field(factory=lambda: np.empty(0))
    velocities: npt.NDArray[np.float64] = attrs.field(factory=lambda: np.empty(0))
    accelerations: npt.NDArray[np.float64] = attrs.field(factory=lambda: np.empty(0))
    color_ids: list[pg.QtGui.QBrush] = attrs.field(factory=list)

    @staticmethod
    def _rms(peak: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        result: npt.NDArray[np.float64] = peak / np.sqrt(2)
        return result

    def display(self, display_type: PeakListDisplayType) -> PeakData:
        return PeakData(
            displacements=self.displacements
            if display_type == PeakListDisplayType.PEAK
            else self._rms(self.displacements),
            frequencies=self.frequencies,
            velocities=self.velocities
            if display_type == PeakListDisplayType.PEAK
            else self._rms(self.velocities),
            accelerations=self.accelerations
            if display_type == PeakListDisplayType.PEAK
            else self._rms(self.accelerations),
            color_ids=self.color_ids,
        )

    def limit(self, limit: Optional[int]) -> PeakData:
        if limit is None:
            return self
        return PeakData(
            displacements=self.displacements[:limit],
            frequencies=self.frequencies[:limit],
            velocities=self.velocities[:limit],
            accelerations=self.accelerations[:limit],
            color_ids=self.color_ids[:limit],
        )

    def sort(self, sorting_method: ReportedPeaksSortingMethod) -> PeakData:
        if sorting_method == ReportedPeaksSortingMethod.DISPLACEMENT:
            sorting_indices = np.argsort(-self.displacements)  # Descending
        elif sorting_method == ReportedPeaksSortingMethod.FREQUENCY:
            sorting_indices = np.argsort(self.frequencies)  # Ascending
        elif sorting_method == ReportedPeaksSortingMethod.VELOCITY:
            sorting_indices = np.argsort(-self.velocities)  # Descending
        elif sorting_method == ReportedPeaksSortingMethod.ACCELERATION:
            sorting_indices = np.argsort(-self.accelerations)  # Descending
        else:
            sorting_indices = np.argsort(-self.displacements)

        return PeakData(
            displacements=self.displacements[sorting_indices],
            frequencies=self.frequencies[sorting_indices],
            velocities=self.velocities[sorting_indices],
            accelerations=self.accelerations[sorting_indices],
            color_ids=list(np.array(self.color_ids)[sorting_indices]),
        )


class VibrationPlot:
    """Vibration measurement plot handler"""

    def __init__(self) -> None:
        self.meas_dist_m: float = 0.0

        self.peak_list_display_type = PeakListDisplayType.PEAK
        self.peak_list_sorting_method = ReportedPeaksSortingMethod.DISPLACEMENT
        self.peak_limit: Optional[int] = None

        self.setup_done = False

    def setup_plot(
        self,
        pg_widget: pg.GraphicsLayoutWidget,
        meas_dist_m: float,
        q_layout: Optional[QLayout] = None,
    ) -> None:
        self.peak_data = PeakData()
        self.meas_dist_m = meas_dist_m

        self.is_plot_plugin = q_layout is not None

        pen_blue = et.utils.pg_pen_cycler(0)
        pen_orange = et.utils.pg_pen_cycler(1)
        brush = et.utils.pg_brush_cycler(0)
        brush_dot = et.utils.pg_brush_cycler(1)
        symbol_kw = dict(symbol="o", symbolSize=1, symbolBrush=brush, symbolPen="k")
        feat_kw_blue = dict(pen=pen_blue, **symbol_kw)
        feat_kw_orange = dict(pen=pen_orange)
        symbol_dot_kw = dict(symbol="o", symbolSize=10, symbolBrush=brush_dot, symbolPen="k")

        # presence plot
        self.object_detection_plot = pg.PlotItem()
        self.object_detection_plot.setMenuEnabled(False)
        self.object_detection_plot.showGrid(x=False, y=True)
        self.object_detection_plot.setLabel("left", "Max amplitude")
        self.object_detection_plot.setLabel("bottom", "Distance (m)")
        self.object_detection_plot.setXRange(meas_dist_m - 0.001, meas_dist_m + 0.001)
        self.presence_curve = self.object_detection_plot.plot(
            **dict(pen=pen_blue, **symbol_dot_kw)
        )

        self.presence_threshold = pg.InfiniteLine(pen=pen_blue, angle=0)
        self.object_detection_plot.addItem(self.presence_threshold)
        self.presence_threshold.show()

        self.smooth_max_presence = et.utils.SmoothMax(tau_decay=10.0)

        # sweep and threshold plot
        self.time_series_plot = pg.PlotItem()
        self.time_series_plot.setMenuEnabled(False)
        self.time_series_plot.showGrid(x=True, y=True)
        self.time_series_plot.setLabel("left", "Displacement (<font>&mu;</font>m)")
        self.time_series_plot.setLabel("bottom", "History")
        self.time_series_curve = self.time_series_plot.plot(**feat_kw_blue)

        self.time_series_plot.setYRange(-1000, 1000)
        self.time_series_plot.setXRange(0, 1024)

        self.text_item_time_series = pg.TextItem(
            fill=pg.mkColor(0xFF, 0x7F, 0x0E, 200),
            anchor=(0.5, 0),
        )
        self.text_item_time_series.hide()
        self.time_series_plot.addItem(self.text_item_time_series)

        sublayout = pg_widget.addLayout(row=0, col=0)
        sublayout.layout.setColumnStretchFactor(0, 4)
        sublayout.layout.setColumnStretchFactor(1, 10)
        sublayout.addItem(self.object_detection_plot, row=0, col=0)
        sublayout.addItem(self.time_series_plot, row=0, col=1)

        self.smooth_lim_time_series = et.utils.SmoothLimits(tau_decay=0.5, tau_grow=0.1)

        self.fft_plot = pg_widget.addPlot(col=0, row=1)
        self.fft_plot.setMenuEnabled(False)
        self.fft_plot.showGrid(x=True, y=True)
        self.fft_plot.setLabel("left", "Displacement (<font>&mu;</font>m)")
        self.fft_plot.setLabel("bottom", "Frequency (Hz)")
        self.fft_plot.setLogMode(False, True)
        self.fft_plot.addItem(pg.PlotDataItem())
        self.fft_curve = [
            self.fft_plot.plot(**feat_kw_blue),
            self.fft_plot.plot(**feat_kw_orange),
            self.fft_plot.plot(**dict(pen=None, **symbol_dot_kw)),
        ]

        self.smooth_max_fft = et.utils.SmoothMax()

        # If we have access to a plot plugin (QWidget-based), we can add a more complex peak list
        # with scrollbar and controls. Otherwise, we add a peak list plot in the GraphicsLayout.
        if self.is_plot_plugin:
            if not self.setup_done:
                assert q_layout is not None
                self._add_peak_list_browser(q_layout)
                self._add_peak_list_controls(q_layout)
                self.setup_done = True
            pg_widget.layout.setRowStretchFactor(0, 1)
            pg_widget.layout.setRowStretchFactor(1, 2)
        else:
            self._add_peak_list_plot(pg_widget)
            pg_widget.layout.setRowStretchFactor(0, 1)
            pg_widget.layout.setRowStretchFactor(1, 2)
            pg_widget.layout.setRowStretchFactor(2, 1)

        self._update_peak_plots()

    def _add_peak_list_plot(self, pg_widget: pg.GraphicsLayoutWidget) -> None:
        self.peak_list_plot = pg.PlotItem()
        self.peak_list_plot.hideAxis("left")
        self.peak_list_plot.hideAxis("bottom")
        self.peak_list_plot.hideButtons()
        self.peak_list_plot.setXRange(0, 10)
        self.peak_list_plot.setYRange(0, 10)
        self.peak_list_plot.setMouseEnabled(False, False)
        self.peak_list_text = pg.TextItem(anchor=(0, 0))
        self.peak_list_text.setPos(0, 10)
        self.peak_list_plot.addItem(self.peak_list_text)

        pg_widget.addItem(self.peak_list_plot, row=2, col=0)

    def _add_peak_list_browser(self, q_layout: QLayout) -> None:
        self.peak_list_browser = QTextBrowser()
        self.peak_list_browser.setLineWrapMode(QTextBrowser.LineWrapMode.NoWrap)
        self.peak_list_browser.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.peak_list_browser.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.peak_list_browser.setFixedHeight(160)
        q_layout.addWidget(self.peak_list_browser)

    def _add_peak_list_controls(self, q_layout: QLayout) -> None:
        self.peak_list_display_combo = QComboBox()
        self.peak_list_sorting_combo = QComboBox()
        self.reported_peaks_limit_combo = QComboBox()

        self.peak_list_display_combo.view().setMinimumWidth(80)
        self.peak_list_sorting_combo.view().setMinimumWidth(140)
        self.reported_peaks_limit_combo.view().setMinimumWidth(140)

        for display_type in PeakListDisplayType:
            self.peak_list_display_combo.addItem(display_type.value, userData=display_type)
        self.peak_list_display_combo.currentIndexChanged.connect(
            self._on_peak_list_display_type_changed
        )

        for sorting_method in ReportedPeaksSortingMethod:
            self.peak_list_sorting_combo.addItem(sorting_method.value, userData=sorting_method)
        self.peak_list_sorting_combo.currentIndexChanged.connect(
            self._on_peak_list_sorting_method_changed
        )

        for limit in ReportedPeaksLimit:
            self.reported_peaks_limit_combo.addItem(limit.value, userData=limit)
        self.reported_peaks_limit_combo.currentIndexChanged.connect(
            self._on_reported_peaks_limit_changed
        )

        peak_list_control_layout = QHBoxLayout()
        peak_list_control_layout.setContentsMargins(0, 0, 0, 0)
        peak_list_control_layout.addWidget(QLabel("Show values as:"))
        peak_list_control_layout.addWidget(self.peak_list_display_combo)
        peak_list_control_layout.addWidget(QLabel("Sort by:"))
        peak_list_control_layout.addWidget(self.peak_list_sorting_combo)
        peak_list_control_layout.addWidget(QLabel("Show:"))
        peak_list_control_layout.addWidget(self.reported_peaks_limit_combo)
        peak_list_control_layout.addStretch()

        self.peak_list_control_container = QWidget()
        self.peak_list_control_container.setLayout(peak_list_control_layout)
        q_layout.addWidget(self.peak_list_control_container)

    def update_plot(
        self,
        result: ExampleAppResult | ProcessorResult,
        extra_result: ProcessorExtraResult,
        show_time_series_std: bool = False,
    ) -> None:
        # Extra result
        time_series = extra_result.zm_time_series
        lp_displacements_threshold = extra_result.lp_displacements_threshold
        amplitude_threshold = extra_result.amplitude_threshold

        # Processor result
        lp_displacements = result.lp_displacements
        lp_displacements_freqs = result.lp_displacements_freqs
        max_amplitude = result.max_sweep_amplitude
        time_series_std = result.time_series_std
        peak_displacements = result.peak_displacements
        peak_frequencies = result.peak_frequencies

        # Plot object presence metric
        self.presence_curve.setData([self.meas_dist_m], [max_amplitude])
        self.presence_threshold.setValue(amplitude_threshold)
        lim = self.smooth_max_presence.update(max_amplitude)
        self.object_detection_plot.setYRange(0, max(1000.0, lim))

        # Plot time series
        if time_series is not None and amplitude_threshold < max_amplitude:
            lim = self.smooth_lim_time_series.update(time_series)
            self.time_series_plot.setYRange(lim[0], lim[1])
            self.time_series_plot.setXRange(0, time_series.shape[0])

            if show_time_series_std and time_series_std is not None:
                self.text_item_time_series.setPos(time_series.size / 2, lim[1] * 0.95)
                time_series_std_str = "{:.0f}".format(time_series_std)
                html_format = (
                    '<div style="text-align: center">'
                    '<span style="color: #FFFFFF;font-size:15pt;">'
                    "{}</span></div>".format("STD : " + time_series_std_str + "<font>&mu;</font>m")
                )
                self.text_item_time_series.setHtml(html_format)
                self.text_item_time_series.show()
            else:
                self.text_item_time_series.hide()
            self.time_series_curve.setData(time_series)

        # Plot spectrum
        if lp_displacements is not None:
            assert time_series is not None
            assert lp_displacements is not None

            self.fft_curve[0].setData(lp_displacements_freqs, lp_displacements)
            self.fft_curve[1].setData(lp_displacements_freqs, lp_displacements_threshold)
            lim = self.smooth_max_fft.update(np.max(lp_displacements))
            self.fft_plot.setYRange(-1, np.log10(lim))

            if len(peak_frequencies) > 0 and len(peak_displacements) > 0:
                self.peak_data = PeakData(
                    displacements=peak_displacements,
                    frequencies=peak_frequencies,
                    velocities=self._velocities(peak_frequencies, peak_displacements),
                    accelerations=self._accelerations(peak_frequencies, peak_displacements),
                    color_ids=[et.utils.pg_brush_cycler(i) for i in range(len(peak_frequencies))],
                )

                self._update_peak_plots()
            else:
                self.fft_curve[2].setData([], [])

    def _on_peak_list_display_type_changed(self, index: int) -> None:
        data = self.peak_list_display_combo.currentData()
        if isinstance(data, PeakListDisplayType):
            self.peak_list_display_type = data
            self._update_peak_plots()

    def _on_peak_list_sorting_method_changed(self, index: int) -> None:
        data = self.peak_list_sorting_combo.currentData()
        if isinstance(data, ReportedPeaksSortingMethod):
            self.peak_list_sorting_method = data
            self._update_peak_plots()

    def _on_reported_peaks_limit_changed(self, index: int) -> None:
        data = self.reported_peaks_limit_combo.currentData()
        if isinstance(data, ReportedPeaksLimit):
            if data == ReportedPeaksLimit.ONE:
                self.peak_limit = 1
            elif data == ReportedPeaksLimit.TEN:
                self.peak_limit = 10
            else:
                self.peak_limit = None
            self._update_peak_plots()

    @staticmethod
    def _velocities(
        frequencies: npt.NDArray[np.float64],
        displacements: npt.NDArray[np.float64],
    ) -> npt.NDArray[np.float64]:
        # Convert to mm/s  (displacement is in µm)
        angular_frequencies = 2 * np.pi * frequencies
        return displacements * angular_frequencies / 1e3

    @staticmethod
    def _accelerations(
        frequencies: npt.NDArray[np.float64],
        displacements: npt.NDArray[np.float64],
    ) -> npt.NDArray[np.float64]:
        # Convert to m/s^2  (displacement is in µm)
        angular_frequencies = 2 * np.pi * frequencies
        return displacements * (angular_frequencies**2) / 1e6

    @staticmethod
    def _cap(word: str) -> str:
        return word if word.isupper() else word.capitalize()

    def _build_peak_table_html(self, peaks: PeakData) -> str:
        BORDER_COLOR = "#7f7f7f"
        HEADER_COLOR = "#1f77b4"
        HIGHLIGHT_BG_COLOR = "#e8f0fe"

        peak_count_unlimited = len(self.peak_data.frequencies)

        if peak_count_unlimited > 1:
            method = self.peak_list_sorting_method
            highlight_disp = method == ReportedPeaksSortingMethod.DISPLACEMENT
            highlight_freq = method == ReportedPeaksSortingMethod.FREQUENCY
            highlight_vel = method == ReportedPeaksSortingMethod.VELOCITY
            highlight_acc = method == ReportedPeaksSortingMethod.ACCELERATION
        else:
            highlight_disp = False
            highlight_freq = False
            highlight_vel = False
            highlight_acc = False

        def cell_style(highlight: bool, extra: str = "") -> str:
            bg = f" background-color: {HIGHLIGHT_BG_COLOR};" if highlight else ""
            return (
                f"border: 1px solid {BORDER_COLOR}; padding: 5px;"
                f" white-space: nowrap;{extra}{bg}"
            )

        # Header row
        label_style = cell_style(False, " color: #282828; text-align: left;")
        label_text = self._cap(self.peak_list_display_type.value)
        header_cells = f"<th style='{label_style}'>{label_text}</th>"

        if peak_count_unlimited > 0:
            for color_id in peaks.color_ids:
                dot_style = cell_style(False, f" color: {color_id.color().name()};")
                header_cells += f"<th style='{dot_style}'>\u25cf</th>"
        else:
            dot_style = cell_style(False, " color: black;")
            header_cells += f"<th style='{dot_style}'>\u25cb</th>"

        # Metric rows
        metric_rows: list[tuple[str, list[str], bool]] = [
            (
                "Displacement (<font>&mu;</font>m)",
                [f"{v:.1f}" for v in peaks.displacements] if peak_count_unlimited > 0 else ["-"],
                highlight_disp,
            ),
            (
                "Frequency (Hz)",
                [f"{v:.1f}" for v in peaks.frequencies] if peak_count_unlimited > 0 else ["-"],
                highlight_freq,
            ),
            (
                "Velocity (mm/s)",
                [f"{v:.1f}" for v in peaks.velocities] if peak_count_unlimited > 0 else ["-"],
                highlight_vel,
            ),
            (
                "Acceleration (m/s\u00b2)",
                [f"{v:.1f}" for v in peaks.accelerations] if peak_count_unlimited > 0 else ["-"],
                highlight_acc,
            ),
        ]

        rows_html = ""
        for label, values, highlight in metric_rows:
            row_header_style = cell_style(highlight, f" color: {HEADER_COLOR}; text-align: left;")
            row = f"<tr><th style='{row_header_style}'>{label}</th>"
            for val in values:
                row += f"<td style='{cell_style(highlight)}'>{val}</td>"
            row += "</tr>"
            rows_html += row

        return (
            "<table style='font-size:10pt; color: black; border-collapse: collapse;'>"
            f"<tr>{header_cells}</tr>"
            f"{rows_html}"
            "</table>"
        )

    def _update_peak_plots(self) -> None:
        peaks = (
            self.peak_data.sort(self.peak_list_sorting_method)
            .display(self.peak_list_display_type)
            .limit(self.peak_limit)
        )

        self.fft_curve[2].setData(
            peaks.frequencies, peaks.displacements, symbolBrush=peaks.color_ids
        )

        html = self._build_peak_table_html(peaks)
        if self.is_plot_plugin:
            self.peak_list_browser.setHtml(html)
        else:
            self.peak_list_text.setHtml(html)
