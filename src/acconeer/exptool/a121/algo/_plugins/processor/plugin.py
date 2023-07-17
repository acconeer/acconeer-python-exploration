# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import abc
from typing import Callable, Generic

import attrs

from acconeer.exptool.a121.algo._base import InputT, MetadataT, ProcessorConfigT, ResultT
from acconeer.exptool.app.new import AppModel, Message, PlotPluginBase, PluginSpecBase

from .backend_plugin import GenericProcessorBackendPluginBase
from .view_plugin import ProcessorViewPluginBase


@attrs.frozen(kw_only=True)
class ProcessorPluginSpec(
    PluginSpecBase, abc.ABC, Generic[InputT, ProcessorConfigT, ResultT, MetadataT]
):
    @abc.abstractmethod
    def create_backend_plugin(
        self, callback: Callable[[Message], None], key: str
    ) -> GenericProcessorBackendPluginBase[InputT, ProcessorConfigT, ResultT, MetadataT]:
        pass

    @abc.abstractmethod
    def create_view_plugin(self, app_model: AppModel) -> ProcessorViewPluginBase[ProcessorConfigT]:
        pass

    @abc.abstractmethod
    def create_plot_plugin(self, app_model: AppModel) -> PlotPluginBase:
        pass
