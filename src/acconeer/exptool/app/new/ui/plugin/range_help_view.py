# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from typing import Optional

from PySide6 import QtCore
from PySide6.QtWidgets import QGridLayout, QGroupBox, QLabel, QLineEdit, QWidget

from acconeer.exptool import a121


class RangeHelpView(QGroupBox):
    APPROX_BASE_STEP_LENGTH_M = 2.5e-3

    def __init__(self, parent: QWidget) -> None:
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

        self.update(None)

    def update(self, subsweep_config: Optional[a121.SubsweepConfig]) -> None:
        if subsweep_config:
            end_point = (
                subsweep_config.start_point
                + (subsweep_config.num_points - 1) * subsweep_config.step_length
            )
            start_m = subsweep_config.start_point * self.APPROX_BASE_STEP_LENGTH_M
            end_m = end_point * self.APPROX_BASE_STEP_LENGTH_M
            step_m = subsweep_config.step_length * self.APPROX_BASE_STEP_LENGTH_M

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
        self.setAlignment(QtCore.Qt.AlignRight)
