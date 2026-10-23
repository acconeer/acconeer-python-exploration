# Copyright (c) Acconeer AB, 2025-2026
# All rights reserved
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QPushButton, QVBoxLayout

from acconeer.exptool.app.new.ui import (
    GroupBox,
    icons,
)


"""
These functions provide saving, loading and creation of Normalization objects.
A noise recording is typically processing independent, so it can be loaded regardless of processor.
The intended usage of these is to be applied in the BackendPlugin,
providing a standardized format for the recorded files.
While a NoiseNormalization can be stored in another format (i.e. along other types of recorded data),
this is the intended way to save them.
"""


class NoiseNormalizationControls(GroupBox[QVBoxLayout]):
    sig_record_clicked = Signal()
    sig_box_clicked = Signal()

    def __init__(self) -> None:
        super().__init__(left_header="Noise Normalization", layout_type=QVBoxLayout)

        self._noise_record_button = QPushButton(icons.PLAY(), "Record Sensor Noise")
        self._noise_record_button.clicked.connect(self.sig_record_clicked)
        self._noise_record_button.setToolTip(
            "Record background noise.\n\nOverwrites the current recording."
        )
        self._apply_norm_check = QCheckBox("Apply noise normalization")
        self._apply_norm_check.clicked.connect(self.sig_box_clicked)
        self._apply_norm_check.setToolTip(
            "If a recording of background noise is available, divide the signal with the noise level."
        )

        self.layout().addWidget(self._apply_norm_check)
        self.layout().setAlignment(self._apply_norm_check, Qt.AlignmentFlag.AlignLeft)
        self.layout().addWidget(self._noise_record_button)

        self._noise_record_button.setEnabled(False)
        self._apply_norm_check.setChecked(False)

    def set_noise_record_button_enabled(self, is_enabled: bool) -> None:
        self._noise_record_button.setEnabled(is_enabled)

    def is_checked(self) -> bool:
        return self._apply_norm_check.isChecked()

    def set_checked(self, is_checked: bool) -> None:
        self._apply_norm_check.setChecked(is_checked)
