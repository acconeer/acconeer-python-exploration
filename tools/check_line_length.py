# Copyright (c) Acconeer AB, 2022
# All rights reserved

import configparser
import fnmatch
import subprocess
import sys


def main():
    config = configparser.ConfigParser()
    config.read("setup.cfg")
    section = "check_line_length"

    line_length = int(config.get(section, "line_length"))
    include = config.get(section, "include", fallback="")
    include = [s.strip() for s in include.split(",")]
    include = [s for s in include if s]

    p = subprocess.run(
        ["git", "ls-files"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
    )

    filenames = p.stdout.decode().splitlines()

    failed = False
    for filename in filenames:
        if not any(fnmatch.fnmatch(filename, p) for p in include):
            continue

        try:
            check(filename, line_length)
        except UnicodeDecodeError:
            pass
        except Exception as e:
            failed = True
            print("{}: {}".format(filename, e))

    return failed


def check(filename, max_line_length):
    with open(filename, "r") as f:
        lines = f.read().splitlines()

    for i, line in enumerate(lines):
        n = len(line)
        if n > max_line_length:
            msg = f"Line {i + 1} too long ({n} > {max_line_length} characters)"
            raise Exception(msg)


if __name__ == "__main__":
    sys.exit(int(main()))
