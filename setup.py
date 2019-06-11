from setuptools import setup, find_packages
from setuptools.command.install import install
from shutil import rmtree


def clean():
    for d in ["build", "dist", "lib/acconeer_utils.egg-info"]:
        rmtree(d, True)


class InstallCommand(install):
    def run(self):
        clean()
        super().run()
        clean()


PACKAGE_ROOT_DIR = "lib"

setup(
    name="acconeer-utils",
    version="2.3.13",
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
