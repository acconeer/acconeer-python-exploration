# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved

from __future__ import annotations

from typing import Optional, Protocol

from PySide6 import QtCore
from PySide6.QtWidgets import QGridLayout, QGroupBox, QLabel, QLineEdit, QWidget


class _RssLikeRangeSpec(Protocol):
    """
    This is a protocol for object that specifies measured
    range in the same way as e.g. ``a121.SubsweepConfig`` does.
    """

    start_point: int
    step_length: int
    num_points: int


class RangeHelpView(QGroupBox):
    APPROX_BASE_STEP_LENGTH_M = 2.5e-3

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self.setTitle("Approx. selected range")

        layout = QGridLayout(self)
        self.setLayout(layout)

        self._start = RangeHelpViewValueWidget(self)
        layout.addWidget(QLabel("Start", self), 0, 0)
        layout.addWidget(self._start, 1, 0)

        self._end = RangeHelpViewValueWidget(self)
        layout.addWidget(QLabel("End", self), 0, 1)
        layout.addWidget(self._end, 1, 1)

        self._step = RangeHelpViewValueWidget(self)
        layout.addWidget(QLabel("Step", self), 0, 2)
        layout.addWidget(self._step, 1, 2)

        self.set_data(None)

    def set_data(self, rsslike_range_spec: Optional[_RssLikeRangeSpec]) -> None:
        if rsslike_range_spec:
            end_point = (
                rsslike_range_spec.start_point
                + (rsslike_range_spec.num_points - 1) * rsslike_range_spec.step_length
            )
            start_m = rsslike_range_spec.start_point * self.APPROX_BASE_STEP_LENGTH_M
            end_m = end_point * self.APPROX_BASE_STEP_LENGTH_M
            step_m = rsslike_range_spec.step_length * self.APPROX_BASE_STEP_LENGTH_M

            self._start.setText(f"{start_m:.3f} m")
            self._end.setText(f"{end_m:.3f} m")
            self._step.setText(f"{step_m * 1e3:.1f} mm")
        else:
            self._start.clear()
            self._step.clear()
            self._end.clear()


class RangeHelpViewValueWidget(QLineEdit):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setEnabled(False)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
