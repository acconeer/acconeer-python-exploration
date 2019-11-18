from setuptools import setup, find_packages
import os


project_dir = os.path.dirname(os.path.realpath(__file__))
version_init_file = os.path.join(project_dir, "src/acconeer/exptool/__init__.py")

with open(version_init_file, "r") as f:
    lines = f.readlines()

for line in lines:
    if line.startswith("__version__"):
        version = line.split("=")[1].strip()[1:-1]
        break
else:
    raise Exception("Could not find the version")

subpackages = find_packages(where="src/acconeer")
packages = ["acconeer." + sp for sp in subpackages]

setup(
    name="acconeer-exptool",
    version=version,
    url="https://github.com/acconeer/acconeer-python-exploration",
    author="Acconeer AB",
    author_email="github@acconeer.com",
    license="BSD",
    package_dir={"": "src"},
    packages=packages,
    zip_safe=False,
    include_package_data=True,
)
