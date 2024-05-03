# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved

import nox


INSTALL_HATCH = """
Hatch can be installed by running

    pipx install hatch

or

    pip3 install --user hatch
"""


@nox.session
def lint(session):
    print("Use 'hatch fmt --check' instead")
    print(INSTALL_HATCH)
    session.error()


@nox.session
def reformat(session):
    print("Use 'hatch fmt' instead")
    print(INSTALL_HATCH)
    session.error()


@nox.session
def mypy(session):
    print("Use 'hatch run mypy:check' instead")
    print(INSTALL_HATCH)
    session.error()


@nox.session
def docs(session):
    print("Use any of these instead")
    print(" - hatch run docs:html")
    print(" - hatch run docs:latexpdf")
    print(" - hatch run docs:rediraffe-check")
    print(" - hatch run docs:rediraffe-write")
    print(INSTALL_HATCH)
    session.error()


@nox.session
def docs_autobuild(session):
    print("Use 'hatch run docs:autobuild' instead")
    print(INSTALL_HATCH)
    session.error()


@nox.session
def test(session):
    print("Use 'hatch test' instead.")
    print("It passes (most of) its arguments straight to pytest!")
    print(INSTALL_HATCH)
    session.error()
