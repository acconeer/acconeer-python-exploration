# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from typing import Any, Optional, Union

import attrs
from typing_extensions import Literal

from acconeer.exptool.app.new._enums import ConnectionState, PluginState


RecipientLiteral = Union[Literal["plot_plugin"], Literal["view_plugin"]]


@attrs.frozen(kw_only=True, slots=False)
class Message:  # Should not be instantiated
    pass


@attrs.frozen(kw_only=True, slots=False)
class ConnectionStateMessage(Message):
    state: ConnectionState = attrs.field()
    warning: Optional[str] = attrs.field(default=None)


@attrs.frozen(kw_only=True, slots=False)
class PluginStateMessage(Message):
    state: PluginState = attrs.field()


@attrs.frozen(kw_only=True, slots=False)
class BackendPluginStateMessage(Message):
    state: Any = attrs.field()


@attrs.frozen(kw_only=True, slots=False)
class StatusMessage(Message):
    status: Optional[str] = attrs.field()


@attrs.frozen(kw_only=True, slots=False)
class LogMessage(Message):
    module_name: str = attrs.field()
    log_level: str = attrs.field()
    log_string: str = attrs.field()


@attrs.frozen(kw_only=True, slots=False)
class GeneralMessage(Message):
    name: str = attrs.field()
    recipient: Optional[RecipientLiteral] = attrs.field(default=None)
    data: Optional[Any] = attrs.field(default=None)
    kwargs: Optional[dict[str, Any]] = attrs.field(default=None)
    exception: Optional[Exception] = attrs.field(default=None)
    traceback_format_exc: Optional[str] = attrs.field(default=None)
