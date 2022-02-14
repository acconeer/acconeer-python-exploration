import argparse
import sys

import nox


py_ver = ".".join(map(str, sys.version_info[:2]))
nox.options.sessions = ["lint", "docs", f"test(python='{py_ver}')"]
nox.options.stop_on_first_error = True
nox.options.reuse_existing_virtualenvs = True


BLACK_SPEC = "black==21.11b1"
ISORT_SPEC = "isort==5.6.3"
PYTEST_MOCK_SPEC = "pytest-mock==3.3.1"

SPHINX_ARGS = ("-QW", "-b", "html", "docs", "docs/_build")


@nox.session
def lint(session):
    session.install(
        BLACK_SPEC,
        ISORT_SPEC,
        "flake8>=4,<5",
        "flake8-mutable",
        "flake8-quotes",
        "flake8-tidy-imports",
    )
    session.run("python", "tools/check_permissions.py")
    session.run("python", "tools/check_whitespace.py")
    session.run("python", "tools/check_line_length.py")
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
def docs(session):
    session.install(".[docs]")
    session.run("python", "-m", "sphinx", *SPHINX_ARGS)


@nox.session
def docs_autobuild(session):
    session.install("-e", ".[docs]")
    session.install("sphinx_autobuild")
    session.run("python", "-m", "sphinx_autobuild", *SPHINX_ARGS, "--watch", "src")


@nox.session
@nox.parametrize("python", ["3.7", "3.8", "3.9", "3.10"])
def test(session):
    KNOWN_GROUPS = ["unit", "integration", "app"]
    DEFAULT_GROUPS = ["unit", "integration"]

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--test-groups",
        nargs="+",
        choices=KNOWN_GROUPS,
        default=DEFAULT_GROUPS,
    )
    parser.add_argument(
        "--integration-args",
        nargs=argparse.REMAINDER,
        default=["--mock"],
    )
    parser.add_argument(
        "--pytest-args",
        nargs=argparse.REMAINDER,
    )
    args = parser.parse_args(session.posargs)

    install_deps = {"pytest"}
    install_extras = set()
    pytest_commands = []

    # Group specific behavior:

    if "unit" in args.test_groups:
        install_deps |= {PYTEST_MOCK_SPEC}
        install_extras |= {"algo"}
        pytest_commands.extend(
            [
                ["-p", "no:pytest-qt", "tests/unit"],
                ["-p", "no:pytest-qt", "tests/processing"],
            ]
        )

    if "integration" in args.test_groups:
        pytest_commands.extend(
            [
                ["-p", "no:pytest-qt", "tests/integration", *args.integration_args],
            ]
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
                ["--timeout=60", "--timeout_method=thread", "tests/gui"],
            ]
        )

    # Override pytest command:

    if args.pytest_args is not None:
        pytest_commands = [args.pytest_args]

    # Install and run:

    install = []

    if install_extras:
        install.append(f".[{','.join(install_extras)}]")
    else:
        install.append(".")

    install.extend(install_deps)

    session.install(*install)

    for cmd in pytest_commands:
        session.run("python", "-m", "pytest", *cmd)
