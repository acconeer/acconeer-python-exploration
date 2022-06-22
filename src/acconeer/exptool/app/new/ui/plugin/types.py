from __future__ import annotations

from typing import Any, Callable, Mapping, Optional, Tuple

from .pidgets import ParameterWidgetFactory


# TODO: Consider removing `Optional[Callable]` if Qt's validators solves the issue.
PidgetFactoryMapping = Mapping[str, Tuple[ParameterWidgetFactory, Optional[Callable[[Any], Any]]]]
