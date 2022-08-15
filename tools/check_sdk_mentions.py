# Copyright (c) Acconeer AB, 2022
# All rights reserved

"""This is a script that checks whether version-strings in the docs are up to date"""

from __future__ import annotations

import configparser
import re
from pathlib import Path
from typing import Dict, List


EXPTOOL_ROOT = Path(__file__).resolve().parents[1]
CONFIG_SECTION = "check_sdk_mentions"


def get_single_match_in_file(pattern: str, file: Path) -> str:
    """Searches the text for a single match to `pattern`. raises if it found none or multiple."""
    matches = re.findall(pattern=pattern, string=file.read_text())

    if len(matches) != 1:
        raise Exception(f"Multiple versions or no version was found in {file}")

    return matches[0]


def get_matches_in_file(pattern: str, path: Path) -> Dict[str, List[str]]:
    """
    Returns a dict on the form
    {
        "<filename>:<lineno>": [<match1>, <match2>, ...],
        ...,
    }
    """
    matches = {}

    for lineno, line in enumerate(path.read_text(encoding="utf8").split("\n"), start=1):
        line_matches = re.findall(pattern=pattern, string=line)
        if line_matches != []:
            matches[f"{path}:{lineno}"] = line_matches

    return matches


def get_matches_in_globs(pattern: str, globs: List[str], root: Path) -> Dict[str, List[str]]:
    matches = {}

    for glob in globs:
        paths = root.glob(glob)
        for path in paths:
            matches.update(get_matches_in_file(pattern, path))

    return matches


def parse_comma_separated_list(comma_separated_list: str) -> List[str]:
    elements = [s.strip() for s in comma_separated_list.split(",")]
    return [s for s in elements if s]


def get_options_from_config(config_file: str = "setup.cfg") -> Dict[str, List[str]]:
    """Loads section CONFIG_SECTION from setup.cfg. raises if it is not present"""
    config = configparser.ConfigParser()
    config.read(config_file)

    if CONFIG_SECTION not in config.sections():
        raise Exception(f'Section "[{CONFIG_SECTION}]" not found in "{config_file}"')

    return {k: parse_comma_separated_list(v) for k, v in config.items(CONFIG_SECTION)}


def check_docs_against_sdk_version(sdk_version: str, pattern_for_docs: str):
    options = get_options_from_config()
    ignore_lines = options.get("ignore_lines", [])
    globs = options.get("include", [])

    doc_mentions = get_matches_in_globs(pattern=pattern_for_docs, globs=globs, root=EXPTOOL_ROOT)

    for ignore_line in ignore_lines:
        # `ignore_line` is suffixed with the lineno, which is added to `EXPTOOL_ROOT`,
        # resulting in a Path that has no file (because of the suffix).
        # It is, however, the expected format from `doc_mentions`'s point of view.
        doc_mentions.pop(str(EXPTOOL_ROOT / ignore_line), None)

    for location, list_of_version_strings in doc_mentions.items():
        if any(ver_str != sdk_version for ver_str in list_of_version_strings):
            raise Exception(
                "There seems to be an outdated SDK version reference here:\n\n"
                + f"    {location}\n\n"
                + 'If you have recently added a semantic-versioning string ("X.Y.Z"), that you\n'
                + 'Do not want to track, make sure to add its source code line to "setup.cfg",\n'
                + f"under [{CONFIG_SECTION}]"
            )


def main():
    SEMVER_PATTERN = r"v?(\d+\.\d+\.\d+)"
    INIT_SDK_VERSION_PATTERN = rf'SDK_VERSION\s*=\s*"{SEMVER_PATTERN}"'

    a111_init_file = EXPTOOL_ROOT / "src" / "acconeer" / "exptool" / "a111" / "__init__.py"
    a111_sdk_version = get_single_match_in_file(INIT_SDK_VERSION_PATTERN, a111_init_file)

    check_docs_against_sdk_version(a111_sdk_version, pattern_for_docs=SEMVER_PATTERN)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(*e.args)
        exit(1)
