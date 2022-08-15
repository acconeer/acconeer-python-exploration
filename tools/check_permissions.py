# Copyright (c) Acconeer AB, 2022
# All rights reserved

import configparser
import fnmatch
import subprocess
import sys


def main():
    config = configparser.ConfigParser()
    config.read("setup.cfg")
    section = "check_permissions"

    default_mode = config.get(section, "default_mode", fallback=None)
    overrides = config.get(section, "overrides", fallback="")

    overrides = [s.strip() for s in overrides.split(",")]
    overrides = [s for s in overrides if s]
    overrides = [s.split(":") for s in overrides]

    if not all([len(s) == 2 for s in overrides]):
        raise Exception

    overrides = dict(overrides)

    p = subprocess.run(
        ["git", "ls-files", "--stage"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
    )

    lines = p.stdout.decode().splitlines()
    failed = False
    for line in lines:
        git_mode, _, _, filename = line.split()
        mode = git_mode[-3:]

        try:
            expected_mode = next(m for p, m in overrides.items() if fnmatch.fnmatch(filename, p))
        except StopIteration:
            expected_mode = default_mode

        if not expected_mode:
            continue

        mask = 0o111  # only check execute bit
        if (int(mode, 8) & mask) != (int(expected_mode, 8) & mask):
            print("{}: has mode {}, expected {}".format(filename, mode, expected_mode))
            failed = True

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
