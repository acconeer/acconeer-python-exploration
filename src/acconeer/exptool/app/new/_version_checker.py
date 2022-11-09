# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from typing import Optional, Tuple

import requests


def check_package_outdated(name: str, current_version: str) -> Tuple[bool, Optional[str]]:

    try:
        response = requests.get(f"https://pypi.python.org/pypi/{name}/json")
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
            "acconeer/acconeer-python-exploration/master/CHANGELOG.md"
        )
        return str(cl.content.decode())
    except Exception:
        return str("### No changelog available at this time")
