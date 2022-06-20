from __future__ import annotations

from typing import Any, Optional, Union

import attrs
from typing_extensions import Literal


StatusLiteral = Union[Literal["ok"], Literal["error"]]
RecipientLiteral = Union[Literal["plot_plugin"], Literal["view_plugin"]]


@attrs.define
class Message:
    status: StatusLiteral
    command_name: str
    recipient: Optional[RecipientLiteral] = attrs.field(default=None, kw_only=True)
    exception: Exception = attrs.field(default=None, init=False)
    data: Any = attrs.field(default=None, init=False)
    traceback_str: Optional[str] = attrs.field(default=None, init=False)


@attrs.define
class OkMessage(Message):
    status: StatusLiteral = attrs.field(default="ok", init=False)


@attrs.define
class ErrorMessage(Message):
    exception: Exception
    traceback_str: Optional[str] = attrs.field(default=None)
    status: StatusLiteral = attrs.field(default="error", init=False)


@attrs.define
class DataMessage(OkMessage):
    data: Any


@attrs.define
class KwargMessage(OkMessage):
    kwargs: dict[str, Any]


@attrs.define
class BusyMessage(OkMessage):
    command_name: str = attrs.field(default="busy")


@attrs.define
class IdleMessage(OkMessage):
    command_name: str = attrs.field(default="idle")


@attrs.define
class BackendPluginStateMessage(OkMessage):
    data: Any = attrs.field()
    command_name: str = attrs.field(default="backend_plugin_state")
