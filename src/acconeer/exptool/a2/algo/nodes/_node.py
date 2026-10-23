# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

from typing import Any, Protocol, TypeVar, runtime_checkable


R_co = TypeVar("R_co", covariant=True)


@runtime_checkable
class Node(Protocol[R_co]):
    """
    Defining the structural interface.
    Any class with an 'execute' method is now a 'Node'.
    """

    def execute(self, /, *args: Any) -> R_co: ...
