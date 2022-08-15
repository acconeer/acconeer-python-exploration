# Copyright (c) Acconeer AB, 2022
# All rights reserved

import sys
from pathlib import Path
from subprocess import DEVNULL, CalledProcessError, check_call


def main():
    here = Path(__file__).resolve().parent

    try:
        check_call([sys.executable, "-m", "pip", "-V"], stdout=DEVNULL, stderr=DEVNULL)
    except CalledProcessError:
        check_call([sys.executable, here / "get-pip.py", "--no-warn-script-location"])

    install_cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--no-warn-script-location",
        "--no-input",
        "--upgrade",
    ]

    if Path("testpypi").is_file():
        install_cmd.extend(
            [
                "--index-url",
                "https://test.pypi.org/simple/",
                "--extra-index-url",
                "https://pypi.org/simple/",
            ]
        )

    install_cmd.append("acconeer-exptool[app]")

    check_call(install_cmd)


if __name__ == "__main__":
    main()
