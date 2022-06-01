from __future__ import annotations

from acconeer.exptool.a121.algo._plugins import (
    ProcessorBackendPlugin,
    ProcessorPlotPlugin,
    ProcessorViewPlugin,
)
from acconeer.exptool.app.new.plugin import Plugin


class SparseIQProcessorBackendPlugin(ProcessorBackendPlugin):
    pass


class SparseIQProcessorPlotPlugin(ProcessorPlotPlugin):
    pass


class SparseIQProcessorViewPlugin(ProcessorViewPlugin):
    pass


SPARSE_IQ_PLUGIN = Plugin(
    key="sparse_iq",
    backend_plugin=SparseIQProcessorBackendPlugin,  # type: ignore[misc]
    plot_plugin=SparseIQProcessorPlotPlugin,  # type: ignore[misc]
    view_plugin=SparseIQProcessorViewPlugin,  # type: ignore[misc]
)
