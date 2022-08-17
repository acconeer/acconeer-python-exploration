# Copyright (c) Acconeer AB, 2022
# All rights reserved
from __future__ import annotations

import logging
from typing import Any, Optional

from acconeer.exptool.app.new.app_model import AppModel, AppModelListener


log = logging.getLogger(__name__)


class UiPluginBase(AppModelListener):
    """Extends AppModelListener by also stopping listening
    when plugins are unloaded (sig_load_plugin emits None).
    """

    def __init__(self, app_model: AppModel) -> None:
        super().__init__(app_model)

        self.__app_model = app_model
        self.__app_model.sig_load_plugin.connect(self._on_load_plugin)
        log.debug(f"{self!s} is now listening to AppModel.")

    def stop_listening(self) -> None:
        super().stop_listening()
        self.__app_model.sig_load_plugin.disconnect(self._on_load_plugin)
        log.debug(f"{self!s} has stopped listening to AppModel.")

    def _on_load_plugin(self, plugin_spec: Optional[Any]) -> None:
        if plugin_spec is None:
            self.stop_listening()
