# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved
from __future__ import annotations

import attrs
import attrs.validators as av
from packaging.version import Version

import acconeer.exptool.type_migration as tm
from acconeer.exptool._core.class_creation.mixins import AttrsMappingTransformsMixin
from acconeer.exptool._core.version_parsing import parse_rss_version


@attrs.frozen
class ServerInfo(AttrsMappingTransformsMixin):
    rss_version: str = attrs.field(validator=av.matches_re(r"a2(11)?-v.*"))
    ticks_per_second: int
    hardware_name: str | None
    sensor_serial: str | None
    max_baudrate: int | None

    @property
    def parsed_rss_version(self) -> Version:
        (_, version) = parse_rss_version(self.rss_version)
        return version


@attrs.frozen
class _ServerInfoNoSerial(AttrsMappingTransformsMixin):
    rss_version: str = attrs.field(validator=av.matches_re(r"a2(11)?-v.*"))
    ticks_per_second: int
    hardware_name: str | None
    max_baudrate: int | None


server_info_timeline = (
    tm.start(_ServerInfoNoSerial)
    .load(dict, _ServerInfoNoSerial.from_dict, fail=[TypeError])
    .load(str, _ServerInfoNoSerial.from_json, fail=tm.common_exceptions.FROM_JSON)
    .nop()
    .epoch(
        ServerInfo,
        lambda old: ServerInfo(
            rss_version=old.rss_version,
            ticks_per_second=old.ticks_per_second,
            hardware_name=old.hardware_name,
            sensor_serial=None,
            max_baudrate=old.max_baudrate,
        ),
        fail=[],
    )
    .load(dict, ServerInfo.from_dict, fail=[TypeError])
    .load(str, ServerInfo.from_json, fail=tm.common_exceptions.FROM_JSON)
)
