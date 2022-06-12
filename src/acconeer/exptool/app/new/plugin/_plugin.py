from __future__ import annotations

import enum
from typing import Optional, Type

import attrs

from acconeer.exptool.app.new.backend import BackendPlugin

from ._plot import PlotPlugin
from ._view import ViewPlugin


class PluginFamily(enum.Enum):
    SERVICE = "Services"
    DETECTOR = "Detectors"


@attrs.frozen(kw_only=True)
class Plugin:
    key: str = attrs.field()
    title: str = attrs.field()
    description: Optional[str] = attrs.field(default=None)
    family: PluginFamily = attrs.field()
    backend_plugin: Type[BackendPlugin] = attrs.field()
    plot_plugin: Type[PlotPlugin] = attrs.field()
    view_plugin: Type[ViewPlugin] = attrs.field()
