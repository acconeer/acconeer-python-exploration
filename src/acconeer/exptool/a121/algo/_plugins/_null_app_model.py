# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import typing as t

from acconeer.exptool.app.new import AppModel


class NullAppModel(AppModel):
    class _NullSignal:
        def connect(self, slot: t.Callable[..., t.Any]) -> None:
            pass

    sig_notify: _NullSignal
    sig_message_plot_plugin: _NullSignal

    def __init__(self) -> None:
        self.sig_notify = self._NullSignal()
        self.sig_message_plot_plugin = self._NullSignal()
        self.sig_backend_state_changed = self._NullSignal()
        self.sig_load_plugin = self._NullSignal()
