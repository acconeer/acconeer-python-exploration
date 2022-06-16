from __future__ import annotations

from typing import Any, Callable, Mapping, Optional, Tuple

from .pidgets import ParameterWidget


# TODO: Consider removing `Optional[Callable]` if Qt's validators solves the issue.
PidgetMapping = Mapping[str, Tuple[ParameterWidget, Optional[Callable[[Any], Any]]]]
