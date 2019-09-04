from setuptools import setup, find_packages
from setuptools.command.install import install
from shutil import rmtree
import os
import sys


def clean():
    for d in ["build", "dist", "lib/acconeer_utils.egg-info"]:
        rmtree(d, True)


class InstallCommand(install):
    def run(self):
        clean()
        super().run()
        clean()


PACKAGE_ROOT_DIR = "lib"

project_root_dir = os.path.dirname(os.path.realpath(__file__))
root_init_file = os.path.join(project_root_dir, "lib/acconeer_utils/__init__.py")

with open(root_init_file, "r") as f:
    lines = f.readlines()

for line in lines:
    if line.startswith("__version__"):
        version = line.split("=")[1].strip()[1:-1]
        break
else:
    sys.stderr.write("Could not find the version number\n")
    sys.exit(1)

setup(
    name="acconeer-utils",
    version=version,
    description="Acconeer utilities",
    url="https://github.com/acconeer/acconeer-python-exploration",
    author="Acconeer AB",
    author_email="github@acconeer.com",
    license="BSD",
    package_dir={"": PACKAGE_ROOT_DIR},
    packages=find_packages(PACKAGE_ROOT_DIR),
    zip_safe=False,
    package_data={"": ["bin/LICENSE.txt", "bin/*.so*", "bin/*/*.dll"]},
    include_package_data=True,
    cmdclass={"install": InstallCommand},
)
