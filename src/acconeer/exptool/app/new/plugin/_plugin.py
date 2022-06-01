from __future__ import annotations

from typing import Type

import attrs

from ._backend import BackendPlugin


@attrs.frozen(kw_only=True)
class Plugin:
    key: str = attrs.field()
    backend_plugin: Type[BackendPlugin] = attrs.field()
