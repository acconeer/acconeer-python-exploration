# Copyright (c) Acconeer AB, 2025-2026
# All rights reserved

from __future__ import annotations

import attrs

from acconeer.exptool import a2
from acconeer.exptool.a2.algo.heatmap.conventional import HeatmapAndSessionConfig, HeatmapConfig
from acconeer.exptool.a2.algo.heatmap.conventional._pidget_mapping import get_config_pidget_mapping
from acconeer.exptool.app.new.ui.resource_tab.event_system import EventBroker

from ._a2_heatmap_config_input import HeatmapPowerConfigEvent, HeatmapPowerConfigInput


@attrs.frozen
class HeatmapConventionalConfigEvent(HeatmapPowerConfigEvent[HeatmapConfig]):
    pass


class HeatmapConventionalConfigInput(
    HeatmapPowerConfigInput[HeatmapConfig, HeatmapConventionalConfigEvent]
):
    def __init__(self, broker: EventBroker, initial_config: HeatmapAndSessionConfig) -> None:
        super().__init__(
            broker,
            initial_config,
            config_type=HeatmapConfig,
            pidget_mapping=get_config_pidget_mapping(),
            id_prefix="a2-conventional",
            title="A2 Conventional config",
        )

    def _create_event(
        self, session_config: a2.SessionConfig, heatmap_config: HeatmapConfig
    ) -> HeatmapConventionalConfigEvent:
        return HeatmapConventionalConfigEvent(
            self.id_, session_config, heatmap_config, *self._power_selections()
        )
