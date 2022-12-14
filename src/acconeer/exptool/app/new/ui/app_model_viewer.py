# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtWidgets import QTextEdit

from acconeer.exptool.app.new.app_model import AppModel


class AppModelViewer(QTextEdit):
    def __init__(self, app_model: AppModel) -> None:
        super().__init__()
        app_model.sig_notify.connect(self._update_text)
        self.setFontFamily("monospace")
        self.setMinimumSize(500, 330)
        self.setReadOnly(True)
        self.update_count = 0

    @staticmethod
    def _stringify_backend_state(backend_state: Optional[Any]) -> list[str]:
        if backend_state is None:
            return ["None"]

        try:
            members = backend_state.__slots__
        except AttributeError:
            members = backend_state.__dict__

        public_members = [member for member in members if not member.startswith("_")]

        return [
            f">>> {attribute}\n" + f"{getattr(backend_state, attribute)}\n"
            for attribute in public_members
        ]

    def _update_text(self, app_model: AppModel) -> None:
        self.update_count += 1
        self.setText(
            "\n".join(
                [
                    "=== AppModel ===",
                    "",
                    f"ConnectionState:          {app_model.connection_state}",
                    f"ConnectionInterface:      {app_model.connection_interface}",
                    f"PluginState:              {app_model.plugin_state}",
                    f"socket_connection_ip:     {app_model.socket_connection_ip}",
                    f"serial_connection_device: {app_model.serial_connection_device}",
                    f"overridden_baudrate:      {app_model.overridden_baudrate}",
                    f"usb_connection_device:    {app_model.usb_connection_device}",
                    "",
                    "backend_plugin_state:",
                    *self._stringify_backend_state(app_model.backend_plugin_state),
                    "",
                    f"Update count:             {self.update_count}",
                ]
            )
        )
