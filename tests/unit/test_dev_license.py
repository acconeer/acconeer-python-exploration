# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import typing as t

import pytest
import requests

from acconeer.exptool import _dev_license
from acconeer.exptool._dev_license import (
    DEV_LICENSE_DEFAULT_CONFIRMATION_MSG,
    DEV_LICENSE_DEFAULT_HEADER,
    DEV_LICENSE_DEFAULT_SUBHEADER,
    DEV_LICENSE_URL,
    DevLicense,
)


class _ErrorResponse:
    text = "<html><body>404 Not Found</body></html>"

    def raise_for_status(self) -> None:
        msg = "404 Client Error"
        raise requests.exceptions.HTTPError(msg)


def test_load_treats_an_http_error_status_as_a_failed_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_dev_license.requests, "get", lambda *a, **k: _ErrorResponse())

    license = DevLicense()
    license.load()

    assert license.html is None


def test_load_treats_a_connection_error_as_a_failed_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get(*args: t.Any, **kwargs: t.Any) -> t.NoReturn:
        raise requests.exceptions.ConnectionError

    monkeypatch.setattr(_dev_license.requests, "get", fake_get)

    license = DevLicense()
    license.load()

    assert license.html is None


@pytest.fixture
def license_with_failed_fetch(monkeypatch: pytest.MonkeyPatch) -> DevLicense:
    monkeypatch.setattr(_dev_license.requests, "get", lambda *a, **k: _ErrorResponse())

    license = DevLicense()
    license.load()
    return license


def test_content_refers_to_the_website_when_the_fetch_failed(
    license_with_failed_fetch: DevLicense,
) -> None:
    assert any(
        DEV_LICENSE_URL in paragraph for paragraph in license_with_failed_fetch.get_content()
    )


def test_content_elements_refers_to_the_website_when_the_fetch_failed(
    license_with_failed_fetch: DevLicense,
) -> None:
    elements = license_with_failed_fetch.get_content_elements()
    assert any(DEV_LICENSE_URL in element for element in elements)


def test_get_header_is_the_default_when_the_fetch_failed(
    license_with_failed_fetch: DevLicense,
) -> None:
    assert license_with_failed_fetch.get_header() == DEV_LICENSE_DEFAULT_HEADER


def test_get_header_element_is_the_default_when_the_fetch_failed(
    license_with_failed_fetch: DevLicense,
) -> None:
    assert (
        license_with_failed_fetch.get_header_element() == f"<h1>{DEV_LICENSE_DEFAULT_HEADER}</h1>"
    )


def test_get_subheader_is_the_default_when_the_fetch_failed(
    license_with_failed_fetch: DevLicense,
) -> None:
    assert license_with_failed_fetch.get_subheader() == DEV_LICENSE_DEFAULT_SUBHEADER


def test_get_subheader_element_is_the_default_when_the_fetch_failed(
    license_with_failed_fetch: DevLicense,
) -> None:
    subheader_element = license_with_failed_fetch.get_subheader_element()
    assert subheader_element == f"<h3>{DEV_LICENSE_DEFAULT_SUBHEADER}</h3>"


def test_get_content_is_the_website_message_when_the_fetch_failed(
    license_with_failed_fetch: DevLicense,
) -> None:
    assert license_with_failed_fetch.get_content() == [DEV_LICENSE_DEFAULT_CONFIRMATION_MSG]


def test_get_content_elements_is_the_website_message_when_the_fetch_failed(
    license_with_failed_fetch: DevLicense,
) -> None:
    content_elements = license_with_failed_fetch.get_content_elements()
    assert content_elements == ["<p></p>", DEV_LICENSE_DEFAULT_CONFIRMATION_MSG]
