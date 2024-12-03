# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved

from __future__ import annotations

import re

from packaging.version import Version


def parse_rss_version(rss_version: str) -> tuple[str, Version]:
    """Takes an RSS version string and returns a corresponding Version

    The RSS version string is on a 'git describe'-like format:

        RL-vA.B.C<-rcD><-E-gF>

    where

        RL: release line
        A:  major
        B:  minor
        C:  micro
        D:  release candidate,
        E:  additional commits since tag, F: commit SHA

    The concept of 'additional commits since tag' (E) doesn't have an
    equivalent in packaging.version.Version. Instead, when E is present,
    the smallest version part (D if present, otherwise C) is bumped and
    E is presented as a development prerelease.

    The commit SHA (F), if present, is translated to a 'local segment'.

    Examples:

    >>> parse_rss_version("a121-v1.2.3")
    ('a121', <Version('1.2.3')>)

    >>> parse_rss_version("a111-v2.10.3-rc4")
    ('a111', <Version('2.10.3rc4')>)

    >>> parse_rss_version("a121-v1.2.3-123-g0e03503be1")
    ('a121', <Version('1.2.4.dev123+g0e03503be1')>)

    >>> parse_rss_version("a121-v1.2.3-rc4-123-g0e03503be1")
    ('a121', <Version('1.2.3rc5.dev123+g0e03503be1')>)

    Read more: https://packaging.pypa.io/en/latest/version.html
    """

    pattern = (
        r"(?P<release_line>a\d{3})-v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<micro>\d+)"
        r"(?:-(?P<pre_phase>rc)(?P<pre_number>\d+))?"
        r"(?:-(?P<dev_number>\d+)-(?P<dev_commit>g\w+))?"
        r"(?:-(dirty))?"
        r".*"
    )
    match = re.fullmatch(pattern, rss_version)
    if not match:
        msg = "Not a valid RSS version"
        raise ValueError(msg)

    groups = match.groupdict()

    is_prerelease = groups["pre_number"] is not None
    is_devrelease = groups["dev_number"] is not None

    release_segment = ""
    pre_segment = ""
    dev_segment = ""

    if is_devrelease:
        dev_segment = f".dev{groups['dev_number']}+{groups['dev_commit']}"

        if is_prerelease:
            groups["pre_number"] = int(groups["pre_number"]) + 1
        else:
            groups["micro"] = int(groups["micro"]) + 1

    if is_prerelease:
        pre_segment = f"{groups['pre_phase']}{groups['pre_number']}"

    release_segment = f"{groups['major']}.{groups['minor']}.{groups['micro']}"

    version = release_segment + pre_segment + dev_segment
    return (groups["release_line"], Version(version))
