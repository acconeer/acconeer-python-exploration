# Copyright (c) Acconeer AB, 2022
# All rights reserved

import shutil
import zipfile
from pathlib import Path

import requests


def main():
    here = Path(__file__).resolve().parent
    package_dir = here / "package"
    package_zip = here / "portable.zip"

    if package_zip.exists():
        return

    path = package_dir / "tools" / "get-pip.py"
    if not path.exists():
        download("https://bootstrap.pypa.io/get-pip.py", path)

    url = "https://www.python.org/ftp/python/3.9.10/python-3.9.10-embed-amd64.zip"
    py_zip_name = url.split("/")[-1]
    py_dir_name = str(Path(py_zip_name).stem)
    py_target_dir = package_dir / "tools" / py_dir_name
    if not py_target_dir.exists():
        py_zip_path = here / py_zip_name
        if not py_zip_path.exists():
            download(url, py_zip_path)

        with zipfile.ZipFile(py_zip_path, "r") as z:
            z.extractall(py_target_dir)

        pth_file = py_target_dir / "python39._pth"

        with open(pth_file, "r") as f:
            contents = f.read()

        if "#import site" in contents:
            with open(pth_file, "w") as f:
                f.write(contents.replace("#import site", "import site"))

    shutil.make_archive(package_zip.with_suffix(""), "zip", package_dir)


def download(url, filename):
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(filename, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)


if __name__ == "__main__":
    main()
