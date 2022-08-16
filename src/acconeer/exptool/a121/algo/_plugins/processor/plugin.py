# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import abc
from typing import Callable, Generic

import attrs

from PySide6.QtWidgets import QWidget

import pyqtgraph as pg

from acconeer.exptool.a121.algo._base import ConfigT, InputT, MetadataT, ResultT
from acconeer.exptool.app.new import AppModel, Message, PluginSpecBase

from .backend_plugin import GenericProcessorBackendPluginBase
from .plot_plugin import GenericProcessorPlotPluginBase
from .view_plugin import ProcessorViewPluginBase


@attrs.frozen(kw_only=True)
class ProcessorPluginSpec(PluginSpecBase, abc.ABC, Generic[InputT, ConfigT, ResultT, MetadataT]):
    @abc.abstractmethod
    def create_backend_plugin(
        self, callback: Callable[[Message], None], key: str
    ) -> GenericProcessorBackendPluginBase[InputT, ConfigT, ResultT, MetadataT]:
        pass

    @abc.abstractmethod
    def create_view_plugin(
        self, app_model: AppModel, view_widget: QWidget
    ) -> ProcessorViewPluginBase[ConfigT]:
        pass

    @abc.abstractmethod
    def create_plot_plugin(
        self, app_model: AppModel, plot_layout: pg.GraphicsLayout
    ) -> GenericProcessorPlotPluginBase[ResultT, MetadataT]:
        pass
