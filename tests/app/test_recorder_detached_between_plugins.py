# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import functools
import time
import typing as t

import pytest

from acconeer.exptool import a2
from acconeer.exptool.a2.algo._plugin_specs.capon_heatmap import CAPON_HEATMAP_PLUGIN
from acconeer.exptool.a2.algo._plugin_specs.sparse_iq import SPARSE_IQ_PLUGIN
from acconeer.exptool.app.new.backend import Backend, ClosedTask, GeneralMessage, MpBackend, Task


pytestmark = pytest.mark.timeout(60)

_NO_WARNING: t.Callable[[t.Any], None] = {}.get


def _run(backend: Backend, task: Task) -> None:
    backend.put_task(task)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        message = backend.recv()
        if isinstance(message, GeneralMessage) and message.exception is not None:
            raise AssertionError(message.traceback_format_exc)
        if isinstance(message, ClosedTask):
            assert message.exception is None, message.traceback_format_exc
            return
    raise TimeoutError


@pytest.mark.parametrize(
    ("client_open", "first", "second"),
    [
        (a2.Client.open, SPARSE_IQ_PLUGIN, CAPON_HEATMAP_PLUGIN),
    ],
    ids=["a2"],
)
def test_plugins_can_record_sessions_back_to_back(
    client_open: t.Callable[..., t.Any], first: t.Any, second: t.Any
) -> None:
    backend = MpBackend()
    backend.start()
    try:
        _run(
            backend,
            (
                "connect_client",
                {
                    "client_factory": functools.partial(client_open, mock=True),
                    "get_connection_warning": _NO_WARNING,
                },
            ),
        )
        for plugin in [first, second]:
            _run(
                backend,
                (
                    "load_plugin",
                    {"plugin_factory": plugin.create_backend_plugin, "key": plugin.key},
                ),
            )
            _run(backend, ("start_session", {"with_recorder": True}))
            _run(backend, ("stop_session", {}))
    finally:
        backend.stop()
