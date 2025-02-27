# Copyright (c) Acconeer AB, 2025
# All rights reserved
"""
pytest is configured to skip these test unless '--test-devsite'
is given on the CLI.

Run only the tests in this file with hatch with the command
$ hatch test tests/flash/test_devsite.py --test-devsite
"""

import os

import pytest

from acconeer.exptool import flash


# Marks all tests in this file as "devsite"
pytestmark = pytest.mark.devsite


@pytest.fixture
def valid_credentials(is_running_in_jenkins: bool) -> tuple[str, str]:
    username = os.getenv("DEV_USERNAME")
    password = os.getenv("DEV_PASSWORD")

    if username is None or password is None:
        if is_running_in_jenkins:
            reason = "DEV_USERNAME & DEV_PASSWORD needs to be specified when running in Jenkins."
            pytest.fail(reason=reason)
        else:
            reason = "Incomplete credentials in env.vars. DEV_USERNAME & DEV_PASSWORD."
            pytest.skip(reason=reason)

    return (username, password)


def test_login_succeeds_with_valid_credentials(valid_credentials: tuple[str, str]) -> None:
    (username, password) = valid_credentials
    cookiejar = flash.login(username, password)
    assert cookiejar is not None


def test_login_fails_with_invalid_credentials() -> None:
    cookiejar = flash.login("example@acconeer.com", "this_is_not_a_real_password")
    assert cookiejar is None


def test_cookiejar_contains_logged_in_cookie(
    valid_credentials: tuple[str, str],
) -> None:
    (username, password) = valid_credentials
    cookiejar = flash.login(username, password)
    assert cookiejar is not None

    found = False
    for k, v in cookiejar.items():
        if "logged_in" in k:
            found = True

    assert found, "No cookie with name '*_logged_in_*' was found in cookiejar."


def test_logged_in_cookie_value_start_with_mangled_username(
    valid_credentials: tuple[str, str],
) -> None:
    (username, password) = valid_credentials
    cookiejar = flash.login(username, password)
    assert cookiejar is not None

    for k, v in cookiejar.items():
        if "logged_in" in k:
            mangled_username = username.replace(".", "-").replace("@", "")
            assert v.startswith(mangled_username + "%")
            break
    else:
        assert False, "No cookie with name '*_logged_in_*' was found in cookiejar."
