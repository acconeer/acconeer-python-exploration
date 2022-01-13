import importlib.util
import os
from glob import glob
from subprocess import check_call


def main():
    root_dir = os.getcwd()
    repo_name = "acconeer-python-exploration"
    repo_dir = os.path.join(root_dir, repo_name)
    repo_addr = "https://github.com/acconeer/acconeer-python-exploration.git"
    python_dir = os.path.abspath(glob("tools\\python-3.7.*")[0])
    python = os.path.abspath(os.path.join(python_dir, "python.exe"))

    # Check that pip is installed
    check_call([python, "-m", "pip", "--version"])
    pip_install = [python, "-m", "pip", "install", "--no-warn-script-location"]

    # Install and import dulwich
    if importlib.util.find_spec("dulwich") is None:
        check_call(pip_install + ["urllib3", "certifi"])
        check_call(pip_install + ["dulwich==0.20.28", "--global-option=--pure"])

    from dulwich import porcelain

    # Clone/clean/update repo
    if os.path.isdir(repo_dir):
        os.chdir(repo_dir)
        porcelain.pull(".", repo_addr)
    else:
        os.chdir(root_dir)
        porcelain.clone(repo_addr, target=repo_dir)

    # Install requirements and acconeer_utils
    os.chdir(repo_dir)
    check_call(pip_install + ["-r", "requirements.txt"])
    check_call(pip_install + ["."])


if __name__ == "__main__":
    main()
