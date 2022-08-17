# Copyright (c) Acconeer AB, 2022
# All rights reserved
#
from .app_model import AppModel


class AppModelListener:
    """A listener of AppModel

    Subclasses needs to do `super().__init__(app_model)` in order
    to set up listening.
    """

    def __init__(self, app_model: AppModel) -> None:
        self.__app_model = app_model
        self.__app_model.sig_notify.connect(self.on_app_model_update)

    def on_app_model_update(self, app_model: AppModel) -> None:
        """Hook for getting updates made to AppModel.

        AppModel calls this function when `AppModel.sig_notify` is emitted,
        i.e. when `AppModel.broadcast` is invoked.
        """
        pass

    def stop_listening(self) -> None:
        """Stops listening to AppModel"""
        self.__app_model.sig_notify.disconnect(self.on_app_model_update)
