# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved

from __future__ import annotations

import requests


_REQUEST_TIMEOUT_S = 10


def check_package_outdated(name: str, current_version: str) -> tuple[bool, str | None]:
    try:
        response = requests.get(
            f"https://pypi.python.org/pypi/{name}/json", timeout=_REQUEST_TIMEOUT_S
        )
        latest_version = response.json()["info"]["version"]
    except Exception:
        latest_version = None
        is_outdated = False
        return is_outdated, latest_version

    if latest_version == current_version:
        is_outdated = False
    else:
        is_outdated = True

    return is_outdated, latest_version


def get_latest_changelog() -> str:
    try:
        cl = requests.get(
            "https://raw.githubusercontent.com/"
            "acconeer/acconeer-python-exploration/master/CHANGELOG.md",
            timeout=_REQUEST_TIMEOUT_S,
        )
        return str(cl.content.decode())
    except Exception:
        return "### No changelog available at this time"
