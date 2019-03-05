from setuptools import setup, find_packages


PACKAGE_ROOT_DIR = "lib"

setup(
    name="acconeer-utils",
    version="2.1.1",
    description="Acconeer utilities",
    url="https://github.com/acconeer/acconeer-python-exploration",
    author="Acconeer AB",
    author_email="github@acconeer.com",
    license="BSD 3-clause",
    package_dir={"": PACKAGE_ROOT_DIR},
    packages=find_packages(PACKAGE_ROOT_DIR),
    zip_safe=True,
)
