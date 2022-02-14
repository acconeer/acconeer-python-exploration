import sys
from pathlib import Path
from subprocess import DEVNULL, CalledProcessError, check_call


def main():
    here = Path(__file__).resolve().parent

    try:
        check_call([sys.executable, "-m", "pip", "-V"], stdout=DEVNULL, stderr=DEVNULL)
    except CalledProcessError:
        check_call([sys.executable, here / "get-pip.py", "--no-warn-script-location"])

    check_call(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-warn-script-location",
            "--no-input",
            "acconeer-exptool[app]",
        ]
    )


if __name__ == "__main__":
    main()
