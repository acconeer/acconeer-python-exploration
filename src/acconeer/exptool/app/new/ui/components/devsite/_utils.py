# Copyright (c) Acconeer AB, 2026
# All rights reserved
from __future__ import annotations

import requests

from acconeer.exptool._artifact_repository import ArtifactRepositoryError


def get_internet_related_error_message(exception: Exception) -> str:
    if isinstance(exception, requests.exceptions.ConnectionError):
        return "Could not reach the Developer Site. Do you have an internet connection?"
    if isinstance(exception, ArtifactRepositoryError):
        return str(exception)
    return (
        "Unexpected error from the Developer Site. Try again later; if it persists, "
        f"report it to Acconeer support. Details: {type(exception).__name__}: {exception}"
    )
