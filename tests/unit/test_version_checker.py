# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import typing as t

import pytest
import requests

from acconeer.exptool.app.new import _version_checker


class _StubResponse:
    content = b"# Changelog"

    @staticmethod
    def json() -> t.Any:
        return {"info": {"version": "1.2.3"}}


def test_requests_are_made_with_a_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, t.Any]] = []

    def fake_get(url: str, **kwargs: t.Any) -> _StubResponse:
        calls.append(kwargs)
        return _StubResponse()

    monkeypatch.setattr(_version_checker.requests, "get", fake_get)

    _version_checker.check_package_outdated("acconeer-exptool", "1.2.3")
    _version_checker.get_latest_changelog()

    assert len(calls) == 2
    assert all(kwargs.get("timeout") for kwargs in calls)


def test_check_package_outdated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_version_checker.requests, "get", lambda url, **kwargs: _StubResponse())

    assert _version_checker.check_package_outdated("acconeer-exptool", "1.2.3") == (False, "1.2.3")
    assert _version_checker.check_package_outdated("acconeer-exptool", "1.0.0") == (True, "1.2.3")


def test_error_paths_fall_back_gracefully(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, **kwargs: t.Any) -> t.NoReturn:
        raise requests.exceptions.Timeout

    monkeypatch.setattr(_version_checker.requests, "get", fake_get)

    assert _version_checker.check_package_outdated("acconeer-exptool", "1.0.0") == (False, None)
    assert "No changelog" in _version_checker.get_latest_changelog()
