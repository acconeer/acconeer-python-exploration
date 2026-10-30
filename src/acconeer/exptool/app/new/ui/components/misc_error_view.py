# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved

from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from acconeer.exptool._core.entities.validation_result import ValidationResult

from .group_box import GroupBox
from .note_label import NoteLabel


class MiscErrorView(GroupBox[QVBoxLayout]):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(
            left_header="Miscellaneous Errors",
            layout_type=QVBoxLayout,
            parent=parent,
        )

        self.setVisible(False)

    def handle_validation_results(
        self, validation_results: list[ValidationResult]
    ) -> list[ValidationResult]:
        self.setVisible(len(validation_results) > 0)

        # Delete all existing error message widgets
        while self.layout().count():
            child = self.layout().takeAt(0)
            if child is None:
                continue
            widget = child.widget()
            if widget is None:
                continue
            widget.deleteLater()

        for result in validation_results:
            error_widget = NoteLabel(parent=self)
            error_widget.set_note(result.message, result.criticality)
            self.layout().addWidget(error_widget)

        return []
