# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import attrs

from acconeer.exptool import a2
from acconeer.exptool.a2.algo.heatmap.coherent import HeatmapAndSessionConfig, HeatmapConfig
from acconeer.exptool.a2.algo.heatmap.coherent._pidget_mapping import get_config_pidget_mapping
from acconeer.exptool.app.new.ui.resource_tab.event_system import EventBroker

from ._a2_heatmap_config_input import HeatmapPowerConfigEvent, HeatmapPowerConfigInput


@attrs.frozen
class HeatmapCoherentConfigEvent(HeatmapPowerConfigEvent[HeatmapConfig]):
    pass


class HeatmapCoherentConfigInput(
    HeatmapPowerConfigInput[HeatmapConfig, HeatmapCoherentConfigEvent]
):
    def __init__(self, broker: EventBroker, initial_config: HeatmapAndSessionConfig) -> None:
        super().__init__(
            broker,
            initial_config,
            config_type=HeatmapConfig,
            pidget_mapping=get_config_pidget_mapping(),
            id_prefix="a2-coherent",
            title="A2 Coherent config",
        )

    def _create_event(
        self, session_config: a2.SessionConfig, heatmap_config: HeatmapConfig
    ) -> HeatmapCoherentConfigEvent:
        return HeatmapCoherentConfigEvent(
            self.id_, session_config, heatmap_config, *self._power_selections()
        )
