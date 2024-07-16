# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved

import configparser
import fnmatch
import subprocess
import sys


def main():
    config = configparser.ConfigParser()
    config.read("setup.cfg")
    section = "check_whitespace"

    ignore_files = config.get(section, "ignore_files", fallback="")
    ignore_files = [s.strip() for s in ignore_files.split(",")]
    ignore_files = [s for s in ignore_files if s]

    p = subprocess.run(
        ["git", "ls-files"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
    )

    filenames = p.stdout.decode().splitlines()

    failed = False
    for filename in filenames:
        if any(True for p in ignore_files if fnmatch.fnmatch(filename, p)):
            continue

        try:
            check(filename)
        except UnicodeDecodeError:
            pass
        except Exception as e:
            failed = True
            print("{}: {}".format(filename, e))

    return failed


def check(filename):
    last_is_empty = False

    with open(filename, "r", newline="") as f:
        for i, line in enumerate(f):
            if line.endswith("\r") or line.endswith("\r\n"):
                msg = "Carriage returns are not allowed"
                raise Exception(msg)

            if not line.endswith("\n"):
                msg = "Missing newline at end of file"
                raise Exception(msg)

            try:
                last_char = line[-2]
            except IndexError:
                last_is_empty = True
            else:
                if last_char.isspace():
                    msg = "Trailing whitespace at end of line {}".format(i + 1)
                    raise Exception(msg)

                last_is_empty = False

    if last_is_empty:
        msg = "Trailing newlines at end of file"
        raise Exception(msg)


if __name__ == "__main__":
    sys.exit(int(main()))
