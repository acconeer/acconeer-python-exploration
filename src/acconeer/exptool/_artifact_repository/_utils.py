# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

from pathlib import Path
from typing import Optional

import requests


def version_from_filename(filename: Optional[str]) -> str:
    """Derives an artifact's version from its filename, e.g. "1.2.3" from "1.2.3.bin"."""
    if filename is None:
        return "n/a"

    return Path(filename).stem


def try_get_obfuscated_email_from_cookiejar(
    cookiejar: Optional[requests.cookies.RequestsCookieJar],
) -> Optional[str]:
    # A cookie in the cookiejar k,v pairs look like this (2025-08-19):
    # k = wordpress_logged_in_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
    # v = firstname-lastnamedomain-com%XXXXXXXXXXXXXXXXXXXXXXXXX...
    # (yes, the "@" is stripped)
    if cookiejar is None:
        return None

    try:
        for k, v in cookiejar.items():
            if "logged_in" in k:
                (mangled_email, *_) = str(v).split("%")
                if mangled_email.count("-") < 2:
                    return (
                        mangled_email[0]
                        + "@".center(len(mangled_email) - 2, "*")
                        + mangled_email[-1]
                    )
                else:
                    leftmost_dash_idx = mangled_email.find("-")
                    rightmost_dash_idx = mangled_email.rfind("-")
                    return (
                        mangled_email[:leftmost_dash_idx]
                        + "@".center(rightmost_dash_idx - leftmost_dash_idx, "*")
                        + mangled_email[rightmost_dash_idx + 1 :]
                    )
    except Exception:
        return None

    return None
