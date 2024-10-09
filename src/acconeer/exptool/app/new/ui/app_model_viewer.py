# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved

from __future__ import annotations

import re
import time
from typing import Any, Optional

from PySide6.QtCharts import QChartView, QLineSeries
from PySide6.QtCore import Qt, SignalInstance
from PySide6.QtGui import QPen, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from acconeer.exptool.app.new.app_model import AppModel


class _CurrentStateView(QTextEdit):
    def __init__(self, app_model: AppModel) -> None:
        super().__init__()
        app_model.sig_notify.connect(self._update_text)
        self.setFontFamily("monospace")
        self.setReadOnly(True)
        self.update_count = 0

    @staticmethod
    def _stringify_backend_state(backend_state: Optional[Any]) -> list[str]:
        if backend_state is None:
            return ["None"]

        try:
            members = backend_state.__slots__
        except AttributeError:
            members = backend_state.__dict__

        public_members = [member for member in members if not member.startswith("_")]

        return [
            f">>> {attribute}\n" + f"{getattr(backend_state, attribute)}\n"
            for attribute in public_members
        ]

    def _update_text(self, app_model: AppModel) -> None:
        self.update_count += 1
        self.setText(
            "\n".join(
                [
                    "=== AppModel ===",
                    "",
                    f"ConnectionState:          {app_model.connection_state}",
                    f"ConnectionInterface:      {app_model.connection_interface}",
                    f"PluginState:              {app_model.plugin_state}",
                    f"PluginGeneration:         {app_model.plugin_generation}",
                    f"socket_connection_ip:     {app_model.socket_connection_ip}",
                    f"serial_connection_device: {app_model.serial_connection_device}",
                    f"overridden_baudrate:      {app_model.overridden_baudrate}",
                    f"usb_connection_device:    {app_model.usb_connection_device}",
                    f"autoconnect_enabled:      {app_model.autoconnect_enabled}",
                    f"flow_control_enabled:     {app_model.flow_control_enabled}",
                    "",
                    "backend_plugin_state:",
                    *self._stringify_backend_state(app_model.backend_plugin_state),
                    "",
                    f"Update count:             {self.update_count}",
                ]
            )
        )


class _SignalLog(QWidget):
    def __init__(self, app_model: AppModel) -> None:
        super().__init__()

        self._model = QStandardItemModel(self)
        self._root = self._model.invisibleRootItem()

        signal_items = (
            self._connect_signal_to_log(app_model.sig_error),
            self._connect_signal_to_log(app_model.sig_load_plugin),
            self._connect_signal_to_log(app_model.sig_message_plot_plugin),
            self._connect_signal_to_log(app_model.sig_message_view_plugin),
            self._connect_signal_to_log(app_model.sig_status_file_path),
            self._connect_signal_to_log(app_model.sig_status_message),
            self._connect_signal_to_log(app_model.sig_rate_stats),
            self._connect_signal_to_log(app_model.sig_frame_count),
            self._connect_signal_to_log(app_model.sig_resource_tab_input_block_requested),
            self._connect_signal_to_log(app_model.sig_backend_state_changed),
        )

        log_view = QTreeView()
        log_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        log_view.setHeaderHidden(True)
        log_view.setModel(self._model)

        clear_button = QPushButton("Clear log")

        def remove_logs() -> None:
            for i in signal_items:
                i.removeRows(0, i.rowCount())

        clear_button.pressed.connect(remove_logs)

        layout = QVBoxLayout()
        layout.addWidget(clear_button)
        layout.addWidget(log_view)
        self.setLayout(layout)

    def _connect_signal_to_log(self, signal: SignalInstance) -> QStandardItem:
        pattern = r"<PySide6.QtCore.SignalInstance ([a-zA-Z_]+).*"
        if (match := re.match(pattern, str(signal))) is None:
            signal_name = "unknown signal"
        else:
            (signal_name,) = match.groups("unknown signal")

        item = QStandardItem(signal_name)
        signal.connect(lambda x: item.appendRow(QStandardItem(str(x))))
        self._root.appendRow(item)
        return item


class _TimingPlot(QChartView):
    def __init__(
        self,
        app_model: AppModel,
        capture_len_s: int = 60,
    ) -> None:
        super().__init__()
        self._capture_len_s = capture_len_s
        self._timing_start = time.perf_counter()

        self._app_model = app_model
        self._app_model.sig_timing.connect(self.plot)
        self.reset()

    def reset(self) -> None:
        self._timing_start = time.perf_counter()
        self.chart().removeAllSeries()

        reference_60_hz = QLineSeries()
        reference_60_hz.setName("Reference: 60Hz")
        pen = QPen(Qt.PenStyle.DashLine)
        pen.setColor("red")
        reference_60_hz.setPen(pen)
        reference_60_hz.append(0, 1000 / 60)
        reference_60_hz.append(self._capture_len_s, 1000 / 60)
        self.chart().addSeries(reference_60_hz)

    @property
    def _timing_series(self) -> list[QLineSeries]:
        return [
            s
            for s in self.chart().series()
            if isinstance(s, QLineSeries)
            # if "reference" not in s.name().lower()
        ]

    def plot(self, name_and_times: tuple[str, float, float]) -> None:
        name, start, end = name_and_times
        timestamp = start - self._timing_start

        if timestamp > self._capture_len_s:
            self.reset()
            self.plot(name_and_times)
            return

        duration_ms = 1000 * (end - start)

        timing_series = self._timing_series
        queried_series = next((s for s in timing_series if s.name() == name), None)

        if queried_series is None:
            new_series = QLineSeries()
            new_series.setName(name)
            new_series.append(timestamp, duration_ms)
            self.chart().addSeries(new_series)
        else:
            queried_series.append(timestamp, duration_ms)

        if timing_series != []:
            max_y = max(p.y() for s in timing_series for p in s.points())
        else:
            max_y = 0

        self.chart().createDefaultAxes()
        self.chart().axisX().setTitleText("Time (s)")
        self.chart().axisY().setTitleText("Elapsed time (ms)")
        self.chart().axisX().setRange(0, self._capture_len_s)
        self.chart().axisY().setRange(0, max(1.1 * max_y, 1))
        self.chart().update()


class _TimingMonitor(QWidget):
    def __init__(self, app_model: AppModel) -> None:
        super().__init__()
        plot = _TimingPlot(app_model)
        reset_button = QPushButton("Reset")
        reset_button.clicked.connect(plot.reset)

        layout = QVBoxLayout()
        layout.addWidget(reset_button)
        layout.addWidget(plot)
        self.setLayout(layout)


class AppModelViewer(QTabWidget):
    def __init__(self, app_model: AppModel) -> None:
        super().__init__()
        self.addTab(_CurrentStateView(app_model), "Current State")
        self.addTab(_SignalLog(app_model), "Signal Log")
        self.addTab(_TimingMonitor(app_model), "Timing Monitor")
        self.setMinimumSize(500, 500)
