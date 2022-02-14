import os
import shutil
import zipfile

import requests


def main():
    here = os.path.dirname(os.path.realpath(__file__))
    package_dir = os.path.join(here, "package")
    package_zip = os.path.join(here, "portable.zip")

    if os.path.isfile(package_zip):
        return

    path = os.path.join(package_dir, "tools", "get-pip.py")
    if not os.path.isfile(path):
        download("https://bootstrap.pypa.io/get-pip.py", path)

    url = "https://www.python.org/ftp/python/3.9.10/python-3.9.10-embed-amd64.zip"
    py_zip_name = url.split("/")[-1]
    py_dir_name = os.path.splitext(py_zip_name)[0]
    py_target_dir = os.path.join(package_dir, "tools", py_dir_name)
    if not os.path.isdir(py_target_dir):
        py_zip_path = os.path.join(here, py_zip_name)
        if not os.path.isfile(py_zip_path):
            download(url, py_zip_path)

        with zipfile.ZipFile(py_zip_path, "r") as z:
            z.extractall(py_target_dir)

    shutil.make_archive(os.path.splitext(package_zip)[0], "zip", package_dir)


def download(url, filename):
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(filename, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)


if __name__ == "__main__":
    main()
