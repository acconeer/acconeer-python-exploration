# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import typing as t

from .app_model import AppModel


class AppModelListener:
    """A listener of AppModel

    Subclasses needs to do `super().__init__(app_model)` in order
    to set up listening.
    """

    def __init__(self, app_model: AppModel) -> None:
        self.__app_model = app_model
        self.__app_model.sig_notify.connect(self.on_app_model_update)
        self.__app_model.sig_backend_state_changed.connect(self.on_backend_state_update)

    def on_app_model_update(self, app_model: AppModel) -> None:
        """Hook for getting updates made to AppModel.

        AppModel calls this function when `AppModel.sig_notify` is emitted,
        i.e. when `AppModel.broadcast` is invoked.
        """
        pass

    def on_backend_state_update(self, backend_plugin_state: t.Optional[t.Any]) -> None:
        """Hook for getting updates made to the backend plugin.

        AppModel calls this function when `AppModel.sig_backend_state_changed` is emitted,
        i.e. when `AppModel.broadcast_backend_state` is invoked.
        """
        pass

    def stop_listening(self) -> None:
        """Stops listening to AppModel"""
        self.__app_model.sig_notify.disconnect(self.on_app_model_update)
        self.__app_model.sig_backend_state_changed.disconnect(self.on_backend_state_update)
