# Copyright (c) Acconeer AB, 2023
# All rights reserved
from __future__ import annotations

import abc
import typing as t
import uuid

import attrs

from PySide6.QtWidgets import QVBoxLayout, QWidget

from acconeer.exptool.app.new.ui.plugin_components.collapsible_widget import CollapsibleWidget

from .common import MaybeIterable, as_sequence
from .pidgets import Pidget


PidgetGroupHook = t.Callable[[QWidget, t.Mapping[str, Pidget]], None]


def _hooks_converter(a: MaybeIterable[PidgetGroupHook]) -> t.Sequence[PidgetGroupHook]:
    return as_sequence(a)


@attrs.frozen(kw_only=True, slots=False)
class PidgetGroup(abc.ABC):
    """The base pidget group."""

    _instance_id: uuid.UUID = attrs.field(factory=uuid.uuid4, init=False)
    """Unique ID for each instance. Enables using otherwise equal instances as hash keys"""

    hooks: t.Sequence[PidgetGroupHook] = attrs.field(factory=tuple, converter=_hooks_converter)
    """Sequence of hooks for this instance"""

    @abc.abstractmethod
    def get_container(self, pidgets: t.Iterable[Pidget]) -> QWidget:
        """Wraps given pidgets in a container that is specified in each subclass"""


@attrs.frozen(kw_only=True, slots=False)
class FlatPidgetGroup(PidgetGroup):
    """A pidget group that only groups widgets hierarchically, not visually"""

    def get_container(self, pidgets: t.Iterable[Pidget]) -> QWidget:
        return _in_a_vboxed_widget(pidgets)


@attrs.frozen(kw_only=True, slots=False)
class CollapsiblePidgetGroup(PidgetGroup):
    """A pidget group that is collapsible"""

    label: str
    collapsed: bool

    def get_container(self, pidgets: t.Iterable[Pidget]) -> QWidget:
        w = CollapsibleWidget(self.label, _in_a_vboxed_widget(pidgets))
        w.set_collapsed(self.collapsed)
        return w


def _in_a_vboxed_widget(widgets: t.Iterable[QWidget]) -> QWidget:
    layout = QVBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(11)

    for widget in widgets:
        layout.addWidget(widget)

    dummy = QWidget()
    dummy.setLayout(layout)
    return dummy
