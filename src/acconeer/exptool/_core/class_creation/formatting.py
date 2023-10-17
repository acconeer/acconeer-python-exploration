# Copyright (c) Acconeer AB, 2023
# All rights reserved

from __future__ import annotations

import enum
import typing as t


def pretty_dict_line_strs(d: dict[str, t.Any], indent: int = 2, width: int = 24) -> list[str]:
    lines = []
    for k, v in d.items():
        if isinstance(v, enum.Enum):
            v = v.name

        lines.append(f"{'':<{indent}}{k + ' ':.<{width}} {v}")

    return lines
