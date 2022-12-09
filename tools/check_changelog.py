# Copyright (c) Acconeer AB, 2022
# All rights reserved

"""This script checks whether CHANGELOG refers to the same version as the current git tag."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional

from packaging.version import Version


def utf8_subprocess_output(*args: str):
    return subprocess.check_output(args, encoding="utf-8").strip()


def get_commit_sha_of_git_tag(git_tag: str):
    return utf8_subprocess_output("git", "rev-list", "-n", "1", git_tag)


def get_current_commit_sha():
    return utf8_subprocess_output("git", "rev-parse", "--verify", "HEAD")


def get_most_recent_git_tag():
    return utf8_subprocess_output("git", "describe", "--abbrev=0", "--tags")


def get_first_match_in_string(pattern: str, string: str, *, group: int = 0) -> Optional[str]:
    """
    Searches for the first match of `pattern` in `string`. Returns `group`:th group (default 0)
    """
    valid_group_numbers = range(0, re.compile(pattern).groups + 1)

    if group not in valid_group_numbers:
        raise ValueError(
            f"`group` is out-of range. group={group} should be "
            + f"in [{valid_group_numbers[0]}, {valid_group_numbers[-1]}]"
        )

    match = re.search(pattern, string)
    return None if (match is None) else match.group(group)


def get_number_of_matches_in_string(pattern: str, string: str) -> int:
    match = re.findall(pattern, string)

    return len(match)


def main():
    VERSION_PATTERN = r"v?\d+\.\d+\.\d+"
    FILE_PATH = "CHANGELOG.md"
    UNRELEASED_FILE_PATH = "UNRELEASED_CHANGELOG.md"
    status = True

    changelog = Path(FILE_PATH)
    unreleased_changelog = Path(UNRELEASED_FILE_PATH)

    if get_number_of_matches_in_string(r"## Unreleased", changelog.read_text()) > 0:
        print("Changelog contains illegal 'Unreleased' headline")
        status = False

    if (
        get_number_of_matches_in_string(r"## " + VERSION_PATTERN, unreleased_changelog.read_text())
        > 0
    ):
        print("Unreleased contains illegal version tag headline")
        status = False

    most_recent_tag = get_most_recent_git_tag()
    most_recent_tag_commit_sha = get_commit_sha_of_git_tag(most_recent_tag)
    current_commit_sha = get_current_commit_sha()

    is_current_commit_tagged = most_recent_tag_commit_sha == current_commit_sha
    if not is_current_commit_tagged:
        exit(0 if status else 1)

    if Version(most_recent_tag).is_prerelease:
        exit(0 if status else 1)

    print(f"Current commit ({current_commit_sha[:7]}) is tagged ({most_recent_tag}).")

    first_match = get_first_match_in_string(VERSION_PATTERN, changelog.read_text())
    print(f'Found "{first_match}" in {FILE_PATH}', end=" ... ")

    is_exact_match = first_match == most_recent_tag
    if is_exact_match:
        print(f"Which matches {most_recent_tag} exactly.")
    else:
        print(f'Which does not match "{most_recent_tag}".')
        status = False

    empty_unreleased_changelog = "# Unreleased Changelog\n\n## Unreleased\n"

    if unreleased_changelog.read_text() != empty_unreleased_changelog:
        print("Unreleased changelog is not cleared")
        status = False

    exit(0 if status else 1)


if __name__ == "__main__":
    main()
