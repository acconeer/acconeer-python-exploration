# Copyright (c) Acconeer AB, 2023
# All rights reserved

from __future__ import annotations

import typing as t

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget


_DataT = t.TypeVar("_DataT")


class DataEditor(QWidget, t.Generic[_DataT]):
    """A DataEditor is a widget that enables a user to edit some data.
    The updated data can be used programmatically and is propagated via
    the `sig_update` Signal or retrieved via `get_data`.
    """

    sig_update = Signal(object)

    def set_data(self, data: t.Optional[_DataT]) -> None:
        """Update the data that is displayed"""
        raise NotImplementedError

    def get_data(self) -> t.Optional[_DataT]:
        """Gets the data stored in the widget"""
        raise NotImplementedError

    @property
    def is_ready(self) -> bool:
        """Returns true if there are any non-validation errors present."""
        raise NotImplementedError

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled and self.get_data() is not None)
