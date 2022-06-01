from __future__ import annotations

from typing import Type

import attrs

from ._backend import BackendPlugin
from ._plot import PlotPlugin
from ._view import ViewPlugin


@attrs.frozen(kw_only=True)
class Plugin:
    key: str = attrs.field()
    backend_plugin: Type[BackendPlugin] = attrs.field()
    plot_plugin: Type[PlotPlugin] = attrs.field()
    view_plugin: Type[ViewPlugin] = attrs.field()
