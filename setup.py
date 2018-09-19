from setuptools import setup

setup(
    name="acconeer-utils",
    version="1.0",
    description="Acconeer utilities",
    url="https://github.com/acconeer/acconeer-python-exploration",
    author="Acconeer AB",
    author_email="github@acconeer.com",
    license="BSD 3-clause",
    packages=["acconeer_utils"],
    install_requires=[
        "numpy",
    ],
    zip_safe=False,
)
