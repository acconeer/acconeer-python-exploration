# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import typing as t

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from .pidgets import PidgetFactory, PidgetGroup


PidgetFactoryMapping = t.Mapping[str, PidgetFactory]
PidgetGroupFactoryMapping = t.Mapping[PidgetGroup, PidgetFactoryMapping]

_DataT = t.TypeVar("_DataT")


class DataEditor(QWidget, t.Generic[_DataT]):
    """A DataEditor is a widget that enables a user to edit some data.
    The updated data can be used programmatically and is propagated via
    the `sig_update` Signal.
    """

    sig_update = Signal(object)

    def set_data(self, data: t.Optional[_DataT]) -> None:
        """Update the data that should be displayed (no extra update of UI)"""
        raise NotImplementedError

    def sync(self) -> None:
        """Forces an update of the view"""
        raise NotImplementedError

    @property
    def is_ready(self) -> bool:
        """Returns true if there are any non-validation errors present."""
        raise NotImplementedError
