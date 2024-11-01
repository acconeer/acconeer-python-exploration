# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved

from __future__ import annotations

import typing as t

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from acconeer.exptool._core.entities.validation_result import ValidationResult


_DataT = t.TypeVar("_DataT")


class DataEditor(t.Generic[_DataT], QWidget):
    """A DataEditor is a widget that enables a user to edit some data.
    The updated data can be used programmatically and is propagated via
    the `sig_update` Signal or retrieved via `get_data`.
    """

    sig_update = Signal(object)

    def set_data(self, data: _DataT) -> None:
        """Update the data that is displayed"""
        raise NotImplementedError

    def get_data(self) -> _DataT:
        """Gets the data stored in the widget"""
        raise NotImplementedError

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled and self.get_data() is not None)

    def handle_validation_results(
        self, validation_results: list[ValidationResult]
    ) -> list[ValidationResult]:
        """Handles validation results by displaying them in the editor in some way.

        Returns ValidationResults that could not be handled.
        """
        raise NotImplementedError

    @property
    def is_ready(self) -> bool:
        """Returns true if there are any non-validation errors present."""
        raise NotImplementedError
