# Copyright (c) Acconeer AB, 2026
# All rights reserved
from __future__ import annotations

import multiprocessing
from typing import Any, Callable

import pytest

from PySide6.QtWidgets import QLabel

from acconeer.exptool import a2, a121
from acconeer.exptool.a2.algo._plugin_specs.sparse_iq import SPARSE_IQ_PLUGIN as A2_SPARSE_IQ
from acconeer.exptool.a121.algo._plugin_specs.sparse_iq import (
    SPARSE_IQ_PLUGIN as A121_SPARSE_IQ,
)
from acconeer.exptool.app.new.backend import GeneralMessage
from acconeer.exptool.app.new.backend._backend_logger import BackendLogger
from acconeer.exptool.app.new.ui.misc import ExceptionWidget


pytestmark = pytest.mark.usefixtures("qapplication")


@pytest.fixture(autouse=True)
def backend_log_sink(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(BackendLogger, "_callback", lambda _: None)


def _a121_sparse_iq() -> tuple[Any, a121.Client]:
    plugin = A121_SPARSE_IQ.create_backend_plugin(callback=lambda _: None, key="sparse_iq")
    client = a121.Client.open(mock=True)
    plugin.attach_client(client=client)
    plugin.restore_defaults()
    return plugin, client


def _a2_sparse_iq() -> tuple[Any, a2.Client]:
    plugin = A2_SPARSE_IQ.create_backend_plugin(callback=lambda _: None, key="sparse_iq")
    client = a2.Client.open(mock=True)
    plugin.attach_client(client=client)
    return plugin, client


def _error_when_the_board_goes_away(
    streaming_plugin: Callable[[], tuple[Any, Any]],
) -> tuple[Exception, str]:
    """The error the GUI gets, and the client's reason for it"""
    plugin, client = streaming_plugin()
    plugin.start_session(with_recorder=False)
    assert plugin.idle()

    client.close()
    with pytest.raises(Exception) as excinfo:
        plugin.idle()
    cause = excinfo.value.__cause__
    assert cause is not None
    assert str(cause) != ""

    # The error reaches the GUI through the backend process' queue
    q: multiprocessing.Queue[GeneralMessage] = multiprocessing.Queue()
    q.put(GeneralMessage(name="error", exception=excinfo.value, traceback_format_exc="tb"))
    exc = q.get(timeout=5).exception
    assert exc is not None
    return exc, str(cause)


@pytest.mark.parametrize(
    "streaming_plugin",
    [
        pytest.param(_a121_sparse_iq, id="a121"),
        pytest.param(_a2_sparse_iq, id="a2"),
    ],
)
def test_error_dialog_names_why_streaming_stopped(
    streaming_plugin: Callable[[], tuple[Any, Any]],
) -> None:
    exc, cause = _error_when_the_board_goes_away(streaming_plugin)
    widget = ExceptionWidget(None, exc=exc, traceback_str="tb")

    texts = [label.text() for label in widget.findChildren(QLabel)]
    assert any(cause in t for t in texts), texts
