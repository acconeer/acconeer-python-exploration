# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from enum import Enum, auto
from typing import Any, Optional

from attrs import define, field


class Criticality(Enum):
    ERROR = auto()
    WARNING = auto()


@define
class ValidationResult(Exception):
    source: Any = field()
    aspect: Optional[str] = field()
    message: str = field()
    criticality: Criticality = field()

    def __attrs_post_init__(self) -> None:
        super(Exception, self).__init__(self.source, self.aspect, self.message, self.criticality)

    def __str__(self) -> str:
        return self.message


@define
class ValidationError(ValidationResult):
    criticality: Criticality = field(default=Criticality.ERROR, init=False)


@define
class ValidationWarning(ValidationResult, Warning):
    criticality: Criticality = field(default=Criticality.WARNING, init=False)

    def __attrs_post_init__(self) -> None:
        super(Warning, self).__init__(self.source, self.aspect, self.message, self.criticality)
