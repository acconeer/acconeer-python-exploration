# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

from enum import Enum, auto
from typing import Tuple

import typing_extensions as te


class Artifact(Enum):
    """The set of artifacts any ``ArtifactRepository`` can download."""

    XC120_EXPLORATION_SERVER = auto()
    XM125_EXPLORATION_SERVER = auto()
    XM126_EXPLORATION_SERVER = auto()
    ALGO_BUNDLE = auto()


class ArtifactRepositoryError(Exception):
    """Base for errors raised by an ``ArtifactRepository``."""


class LoginRequiredError(ArtifactRepositoryError):
    """Raised by ``download()`` when there is no valid, logged-in session.

    Callers that catch this should route the user back through ``login()``;
    anything else raised by ``download()`` is an unrelated failure.
    """


class ArtifactRepository(te.Protocol):
    """The interface a repository needs to follow to serve the flash wizard/CLI."""

    def get_user_representation(self) -> str | None: ...

    def login(self, email: str, password: str, remember_me: bool = False) -> None: ...

    def forget_login(self) -> None: ...

    def has_logged_in_previously(self) -> bool:
        """Whether locally saved credentials exist, without checking they still work.

        ``download()`` is the authority on whether a session is actually
        still valid; it raises ``LoginRequiredError`` when it isn't.
        """
        ...

    def download(self, artifact: Artifact, path: str) -> Tuple[str, str]: ...
