# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from acconeer.exptool._core.entities.validation_result import Criticality, ValidationResult


class MiscErrorView(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)

        self.setLayout(QVBoxLayout(self))
        self.layout().setContentsMargins(0, 0, 0, 0)

    def handle_validation_results(
        self, validation_results: list[ValidationResult]
    ) -> list[ValidationResult]:
        COLOR_MAP = {
            Criticality.ERROR: "#E6635A",
            Criticality.WARNING: "#FCC842",
            None: "white",
        }

        # Delete all existing error message widgets
        while self.layout().count():
            child = self.layout().takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        for result in validation_results:
            error_widget = QLabel(parent=self)
            error_widget.setWordWrap(True)
            error_widget.setContentsMargins(5, 5, 5, 5)
            error_widget.setText(result.message)
            error_widget.setStyleSheet(
                f"background-color: {COLOR_MAP[result.criticality]}; "
                "color: white; font: bold italic;"
            )
            self.layout().addWidget(error_widget)

        return []
