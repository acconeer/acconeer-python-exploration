from __future__ import annotations

from typing import Generic, Type

import attrs

from acconeer.exptool.a121.algo._base import ConfigT, InputT, MetadataT, ResultT
from acconeer.exptool.app.new import Plugin

from .backend_plugin import GenericProcessorBackendPluginBase
from .plot_plugin import GenericProcessorPlotPluginBase
from .view_plugin import ProcessorViewPluginBase


@attrs.frozen(kw_only=True)
class ProcessorPlugin(Plugin, Generic[InputT, ConfigT, ResultT, MetadataT]):
    backend_plugin: Type[
        GenericProcessorBackendPluginBase[InputT, ConfigT, ResultT, MetadataT]
    ] = attrs.field()
    plot_plugin: Type[GenericProcessorPlotPluginBase[ResultT, MetadataT]] = attrs.field()
    view_plugin: Type[ProcessorViewPluginBase[ConfigT]] = attrs.field()
