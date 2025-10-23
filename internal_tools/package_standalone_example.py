# Copyright (c) Acconeer AB, 2025
# All rights reserved

import argparse
import datetime
import subprocess as sp
import tempfile
import zipfile
from pathlib import Path


PROLOGUE = """
The aim of this script is to package standalone examples that are dependant on acconeer-exptool
(typically PGUpdater-based examples, but might be applicable for other types of examples)
into an as-isolated-as-possible package.

Also, the packaging should include double-click scripts that launches the example.

The script performs the following steps:
1. Generate a generic README
2. Build a wheel acconeer-exptool of the checked-out version
3. Generate double-clickable scripts for both Linux (bash) and Windows (batch, ".bat")
4. Puts the wheel, the double-clickable scripts and the example .py file and other specified resource files in a zip archive.

NOTE: The zip always contains a folder with the same name as the zip itself.
"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description=PROLOGUE,
        epilog="Example: $ python internal_tools/package_standalone_example.py examples/a121/plot.py --resource README.md:a/b/c/README.md",
    )
    parser.add_argument("example_path")
    parser.add_argument(
        "--resource",
        action="append",
        dest="resources",
        default=[],
        help="Resources to include in the zip archive. Specified like '--resource <src_path>:<archive_path>'. Can be repeated",
    )

    args = parser.parse_args()

    example_path = Path(args.example_path)
    if not example_path.is_file():
        print(f"Cannot find file '{example_path}'")
        exit(1)

    for i, resource in enumerate(args.resources):
        if resource.count(":") != 1:
            print(f"Each --resource should have exactly 1 ':', was {resource!r}")
            exit(1)
        (src_path, _) = resource.split(":")
        if not Path(src_path).is_file():
            print(f"Cannot find resource file {i}, {resource!r}")
            exit(1)

    resources = [tuple(map(Path, mapping.split(":"))) for mapping in args.resources]

    zip_example_part = "".join(c if c.isalnum() else "-" for c in example_path.as_posix())
    git_description = sp.check_output(["git", "describe", "--tags"], text=True).strip()

    output_zip = Path(
        f"./acconeer_exptool_with_{zip_example_part}_{git_description}_{datetime.date.today()}.zip"
    )

    with tempfile.TemporaryDirectory() as build_dir_strpath:
        build_dir = Path(build_dir_strpath)

        print("--- Building wheel")
        _ = sp.check_call(["hatch", "build", "--target", "wheel", build_dir])
        (et_wheel_path,) = build_dir.glob("*.whl")

        print("--- Generating double-click scripts")
        linux_run_app_path = build_dir / "run_app.bash"
        linux_run_app_path.write_text(
            LINUX_BASH_DOUBLE_CLICK_SCRIPT_CONTENT.format(
                example_file_name=example_path.name,
                et_wheel_file_name=et_wheel_path.name,
            )
        )
        linux_run_app_path.chmod(0o777)

        windows_run_app_path = build_dir / "run_app.bat"
        windows_run_app_path.write_text(
            WINDOWS_BATCH_DOUBLE_CLICK_SCRIPT_CONTENT.format(
                example_file_name=example_path.name,
                et_wheel_file_name=et_wheel_path.name,
            )
        )

        print("--- Generating README")
        readme_path = build_dir / "README.txt"
        readme_path.write_text(README_CONTENT)

        print("--- Zipping")
        # sorting out archive paths
        arcdir = Path(output_zip.with_suffix("").name)  # archive root dir
        readme_archive_path = arcdir / readme_path.name
        example_archive_path = arcdir / example_path.name
        et_wheel_archive_path = arcdir / et_wheel_path.name
        linux_run_app_archive_path = arcdir / linux_run_app_path.name
        windows_run_app_archive_path = arcdir / windows_run_app_path.name

        with zipfile.ZipFile(output_zip, "w") as zip:
            zip.write(filename=readme_path, arcname=readme_archive_path)
            zip.write(filename=et_wheel_path, arcname=et_wheel_archive_path)
            zip.write(filename=example_path, arcname=example_archive_path)
            zip.write(filename=linux_run_app_path, arcname=linux_run_app_archive_path)
            zip.write(filename=windows_run_app_path, arcname=windows_run_app_archive_path)

            for src_path, archive_path in resources:
                zip.write(filename=src_path, arcname=arcdir / archive_path)

        print(f"Successfully created {output_zip}")


README_CONTENT = """\
Windows users
=============
Double-click "run_app.bat".

Linux users
===========
Double-click "run_app.bash".

If that doesn't start executing the script, try:

1. Right click on "run_app.bash"
2. In the right-click menu, click "Run as a Program" (tested on Ubuntu 24.04)

Or run the script from the terminal:

$ ./run_app.bash
"""

LINUX_BASH_DOUBLE_CLICK_SCRIPT_CONTENT = """\
#!/usr/bin/env bash

echo "--- Trying to install python3 with apt ..."
sudo apt install python3
if [ $? -gt 0 ]; then
    read -p "Press ENTER to exit"
    exit 1
fi

echo "--- Trying to install the virtualenv package with pip ..."
python3 -m pip install virtualenv
if [ $? -gt 0 ]; then
    echo "--- No pip detected. attempting to install python3-virtualenv via apt ..."
    sudo apt install python3-virtualenv
    if [ $? -gt 0 ]; then
        read -p "Press ENTER to exit"
        exit 1
    fi
fi

echo "--- Creating virtualenv with name run_app_venv ..."
python3 -m virtualenv run_app_venv
if [ $? -gt 0 ]; then
    read -p "Press ENTER to exit"
    exit 1
fi

echo "--- Activating virtualenv with name run_app_venv ..."
source ./run_app_venv/bin/activate
if [ $? -gt 0 ]; then
    read -p "Press ENTER to exit"
    exit 1
fi

echo "--- Installing acconeer-exptool with its dependencies ..."
python3 -m pip install "{et_wheel_file_name}[app]"
if [ $? -gt 0 ]; then
    read -p "Press ENTER to exit"
    exit 1
fi

echo "--- Starting {example_file_name} ..."
python3 {example_file_name}
if [ $? -gt 0 ]; then
    read -p "Press ENTER to exit"
    exit 1
fi
"""

WINDOWS_BATCH_DOUBLE_CLICK_SCRIPT_CONTENT = """\
@echo off

echo --- Trying to install virtualenv with system-level pip ...
python -m pip install virtualenv
if %errorlevel% neq 0 (
    echo Press ENTER to exit
    pause
    exit
)

echo --- Creating virtualenv with name run_app_venv ...
python -m virtualenv run_app_venv
if %errorlevel% neq 0 (
    echo Press ENTER to exit
    pause
    exit
)

echo --- Activating virtualenv with name run_app_venv ...
call run_app_venv\\Scripts\\activate.bat
if %errorlevel% neq 0 (
    echo Press ENTER to exit
    pause
    exit
)

echo --- Installing acconeer-exptool with its dependencies ...
python -m pip install {et_wheel_file_name}[app]
if %errorlevel% neq 0 (
    echo Press ENTER to exit
    pause
    exit
)

echo --- Starting {example_file_name} ...
python {example_file_name}
if %errorlevel% neq 0 (
    echo Press ENTER to exit
    pause
    exit
)
"""


if __name__ == "__main__":
    main()
