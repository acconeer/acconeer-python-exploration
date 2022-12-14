# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from typing import Optional, Union

from PySide6 import QtCore
from PySide6.QtWidgets import QGridLayout, QGroupBox, QLabel, QLineEdit, QStackedLayout, QWidget

from acconeer.exptool import a121

from .utils import VerticalGroupBox


_WIDGET_WIDTH = 125


class SmartPerfCalcView(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)

        self._layout = QStackedLayout()
        self.setLayout(self._layout)

        self._perf_calc_view = PerfCalcView(self)
        self._extended_perf_calc_view = ExtendedPerfCalcView(self)
        self._layout.addWidget(self._perf_calc_view)
        self._layout.addWidget(self._extended_perf_calc_view)

    def update(
        self,
        session_config: Optional[a121.SessionConfig] = None,
        metadata: Optional[Union[a121.Metadata, list[dict[int, a121.Metadata]]]] = None,
    ) -> None:
        if isinstance(metadata, list):
            self._layout.setCurrentIndex(1)
            self._extended_perf_calc_view.update(session_config, metadata)
        else:
            self._layout.setCurrentIndex(0)
            self._perf_calc_view.update(session_config, metadata)


class ExtendedPerfCalcView(VerticalGroupBox):
    def __init__(self, parent: QWidget) -> None:
        super().__init__("Performance calculations", parent)

        label = QLabel("No estimates available", self)
        label.setEnabled(False)
        label.setAlignment(QtCore.Qt.AlignCenter)
        self.layout().addWidget(label)

    def update(
        self,
        session_config: Optional[a121.SessionConfig] = None,
        extended_metadata: Optional[list[dict[int, a121.Metadata]]] = None,
    ) -> None:
        pass


class PerfCalcView(QGroupBox):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)

        self.setTitle("Performance estimates")

        tooltip = (
            "The estimate is based on calculations and "
            "conservative measurements in room temperature."
        )

        layout = QGridLayout(self)
        self.setLayout(layout)

        self.average_current = PerfCalcValueWidget(self)
        layout.addWidget(self.average_current, 0, 1)
        average_current_label = QLabel("Estimated avg. current", self)
        average_current_label.setToolTip(tooltip)
        layout.addWidget(average_current_label, 0, 0)

        self.update(None)

    def update(
        self,
        session_config: Optional[a121.SessionConfig] = None,
        metadata: Optional[a121.Metadata] = None,
    ) -> None:
        try:
            self._update(session_config, metadata)
        except Exception:
            pass
        else:
            return

        self.average_current.setText("-")

    def _update(
        self,
        session_config: Optional[a121.SessionConfig] = None,
        metadata: Optional[a121.Metadata] = None,
    ) -> None:
        if session_config is None or metadata is None:
            raise ValueError

        pc = a121._SensorPerformanceCalc(
            session_config.sensor_config, metadata, session_config.update_rate
        )

        self.average_current.setText(f"{pc.average_current * 1e3:.0f} mA")


class PerfCalcValueWidget(QLineEdit):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAlignment(QtCore.Qt.AlignRight)
        self.setFixedWidth(_WIDGET_WIDTH)
        self.setReadOnly(True)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
