import os
from glob import glob
from subprocess import CalledProcessError, check_call


def main():
    python_dir = os.path.abspath(glob("tools\\python-3.*")[0])
    os.chdir(python_dir)

    try:
        check_call([".\\python.exe", "-m", "pip", "--version"])
    except CalledProcessError:
        check_call([".\\python.exe", "..\\get-pip.py", "--no-warn-script-location"])


if __name__ == "__main__":
    main()
