# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved

import nox


@nox.session
def lint(session):
    session.error("Use 'hatch run lint:check' instead")


@nox.session
def reformat(session):
    session.error("Use 'hatch run lint:reformat' instead")


@nox.session
def mypy(session):
    session.error("Use 'hatch run mypy:check' instead")


@nox.session
def docs(session):
    session.error(
        "Use any of these instead",
        "hatch run docs:html",
        "hatch run docs:latexpdf",
        "hatch run docs:rediraffe-check",
        "hatch run docs:rediraffe-write",
    )


@nox.session
def docs_autobuild(session):
    session.error("Use 'hatch run docs:autobuild' instead")


@nox.session
def test(session):
    session.error(
        "Use a script in environments 'test' instead",
        "See all available by running 'hatch env show'",
    )
