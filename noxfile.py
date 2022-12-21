# Copyright (c) Acconeer AB, 2022
# All rights reserved

import argparse
import sys

import nox


py_ver = ".".join(map(str, sys.version_info[:2]))
nox.options.sessions = ["lint", "docs", f"test(python='{py_ver}')"]
nox.options.stop_on_first_error = True
nox.options.reuse_existing_virtualenvs = True


BLACK_SPEC = "black==22.12.0"
ISORT_SPEC = "isort==5.6.3"
MYPY_SPEC = "mypy==0.991"
PIP_SPEC = "pip>=21.3"
PYTEST_MOCK_SPEC = "pytest-mock==3.3.1"
PYTEST_SPEC = "pytest==7.2"
PYTEST_XDIST_SPEC = "pytest-xdist==3.1.0"

SPHINX_SOURCE_DIR = "docs"
SPHINX_OUTPUT_DIR = "docs/_build"
SPHINX_HTML_ARGS = ("-b", "html", SPHINX_SOURCE_DIR, SPHINX_OUTPUT_DIR)


class Parser(argparse.ArgumentParser):
    KNOWN_TEST_GROUPS = ["unit", "integration", "app"]
    DEFAULT_TEST_GROUPS = ["unit", "integration"]

    KNOWN_DOCS_BUILDERS = ["html", "latexpdf", "rediraffecheckdiff", "rediraffewritediff"]
    DEFAULT_DOCS_BUILDERS = ["html"]

    def __init__(self):
        super().__init__()

        self.add_argument(
            "-e",
            "--editable",
            action="store_true",
            default=False,
        )

        test_group = self.add_argument_group("test")
        test_group.add_argument(
            "--test-groups",
            nargs="+",
            choices=self.KNOWN_TEST_GROUPS,
            default=self.DEFAULT_TEST_GROUPS,
        )
        test_group.add_argument(
            "--integration-args",
            nargs=argparse.REMAINDER,
            default=["a111", "--mock"],
        )
        test_group.add_argument(
            "--pytest-args",
            nargs=argparse.REMAINDER,
        )

        docs_group = self.add_argument_group("docs")
        docs_group.add_argument(
            "--docs-builders",
            nargs="+",
            choices=self.KNOWN_DOCS_BUILDERS,
            default=self.DEFAULT_DOCS_BUILDERS,
        )


@nox.session
def lint(session):
    session.install(
        BLACK_SPEC,
        ISORT_SPEC,
        "flake8>=4,<5",
        "flake8-future-annotations",
        "flake8-mutable",
        "flake8-quotes",
        "flake8-tidy-imports",
        "packaging",
    )
    session.run("python", "tools/check_permissions.py")
    session.run("python", "tools/check_whitespace.py")
    session.run("python", "tools/check_line_length.py")
    session.run("python", "tools/check_sdk_mentions.py")
    session.run("python", "tools/check_changelog.py")
    session.run("python", "tools/check_copyright.py")
    session.run("python", "-m", "flake8")
    session.run("python", "-m", "black", "--check", "--diff", "--quiet", ".")
    session.run("python", "-m", "isort", "--check", "--diff", "--quiet", ".")


@nox.session
def reformat(session):
    session.install(
        BLACK_SPEC,
        ISORT_SPEC,
    )
    session.run("python", "-m", "black", ".")
    session.run("python", "-m", "isort", ".")


@nox.session
def mypy(session):
    args = Parser().parse_args(session.posargs)

    if args.editable:
        session.install("-e", ".")
    else:
        session.install(".")

    session.install(MYPY_SPEC, PYTEST_SPEC)
    session.run("python", "-m", "mypy", "-p", "acconeer.exptool.a121")
    session.run("python", "-m", "mypy", "-p", "acconeer.exptool.app.new")
    session.run("python", "-m", "mypy", "-p", "acconeer.exptool.setup")
    session.run("python", "-m", "mypy", "tests/unit/a121")


@nox.session
def docs(session):
    args = Parser().parse_args(session.posargs)

    if args.editable:
        session.install(PIP_SPEC)
        session.install("-e", ".[docs]")
    else:
        session.install(".[docs]")

    if "html" in args.docs_builders:
        session.run("python", "-m", "sphinx", "-W", *SPHINX_HTML_ARGS)

    if "latexpdf" in args.docs_builders:
        session.run(
            "python",
            "-m",
            "sphinx",
            "-M",
            "latexpdf",
            SPHINX_SOURCE_DIR,
            SPHINX_OUTPUT_DIR,
        )

    if "rediraffewritediff" in args.docs_builders:
        session.run(
            "python",
            "-m",
            "sphinx",
            "-b",
            "rediraffewritediff",
            SPHINX_SOURCE_DIR,
            SPHINX_OUTPUT_DIR,
        )

    if "rediraffecheckdiff" in args.docs_builders:
        session.run(
            "python",
            "-m",
            "sphinx",
            "-b",
            "rediraffecheckdiff",
            SPHINX_SOURCE_DIR,
            SPHINX_OUTPUT_DIR,
        )


@nox.session
def docs_autobuild(session):
    session.install(PIP_SPEC)
    session.install("-e", ".[docs]")
    session.install("sphinx_autobuild")
    session.run("python", "-m", "sphinx_autobuild", *SPHINX_HTML_ARGS, "--watch", "src")


@nox.session
@nox.parametrize("python", ["3.7", "3.8", "3.9", "3.10", "3.11"])
def test(session):
    args = Parser().parse_args(session.posargs)

    install_deps = {PYTEST_SPEC, PYTEST_XDIST_SPEC}
    install_extras = set()
    pytest_commands = []

    # Group specific behavior:

    if "unit" in args.test_groups:
        install_deps |= {PYTEST_MOCK_SPEC}
        install_extras |= {"algo"}
        pytest_commands.extend(
            [
                ["-n", "auto", "-p", "no:pytest-qt", "tests/unit"],
                ["-n", "auto", "-p", "no:pytest-qt", "tests/processing"],
            ]
        )

    if "integration" in args.test_groups:
        real_args = [arg for arg in args.integration_args if arg not in {"a111", "a121"}]
        if "a111" in args.integration_args:
            pytest_commands.extend(
                [
                    ["-p", "no:pytest-qt", "tests/integration/a111", *real_args],
                ]
            )
        elif "a121" in args.integration_args:
            pytest_commands.extend(
                [
                    ["-p", "no:pytest-qt", "tests/integration/a121", *real_args],
                ]
            )
        else:
            session.error(
                "The 'integration' session needs to be passed"
                + "either 'a121' or 'a111' in its '--integration-args'"
            )

    if "app" in args.test_groups:
        install_deps |= {
            PYTEST_MOCK_SPEC,
            "pytest-qt",
            "pytest-timeout",
            "requests",
        }
        install_extras |= {"app"}
        pytest_commands.extend(
            [
                ["--timeout=120", "--timeout_method=thread", "tests/gui"],
            ]
        )

    # Override pytest command:

    if args.pytest_args is not None:
        pytest_commands = [args.pytest_args]

    # Install and run:

    install = []

    if args.editable:
        session.install(PIP_SPEC)
        install.append("-e")

    if install_extras:
        install.append(f".[{','.join(install_extras)}]")
    else:
        install.append(".")

    install.extend(install_deps)

    session.install(*install)

    for cmd in pytest_commands:
        session.run("python", "-m", "pytest", *cmd)
