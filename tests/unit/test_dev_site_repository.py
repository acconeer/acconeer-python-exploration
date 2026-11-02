# Copyright (c) Acconeer AB, 2026
# All rights reserved
from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path

import pytest
import requests

from acconeer.exptool._artifact_repository import Artifact, DevSiteRepository
from acconeer.exptool._artifact_repository._dev_site_repository import DEFAULT_BASE_URL


_COOKIE_NAME = "wordpress_logged_in_test"
_SW_PAGE_URL = f"{DEFAULT_BASE_URL}/home/a121-docs-software/"
_DEVICE_PAGE_URL = f"{DEFAULT_BASE_URL}/xe121-page/"
_ZIP_URL = "https://cdn.example.com/xc120_exploration_server_v1.2.3.zip"
_FILENAME = "xc120_exploration_server_v1.2.3.zip"


class _FakeResponse:
    def __init__(
        self, url: str | None = None, headers: dict[str, str] | None = None, content: bytes = b""
    ) -> None:
        self.url = url
        self.headers = headers or {}
        self.content = content


def _zip_with_bin(name: str, data: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(name, data)
    return buf.getvalue()


def test_download_keeps_using_cookies_cleared_from_under_it_mid_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A concurrent forget_login() must not be able to turn an in-flight
    download() into an unauthenticated request: the session it already
    started using has to keep the cookies it began with.
    """
    cookies = requests.cookies.RequestsCookieJar()
    cookies.set(_COOKIE_NAME, "secret-session-value")
    repo = DevSiteRepository(cookies=cookies)

    zip_bytes = _zip_with_bin("firmware.bin", b"binary-data")
    calls: list[tuple[str, str, dict[str, str]]] = []

    def fake_get(
        self: requests.Session, url: str, cookies: dict[str, str] | None = None
    ) -> _FakeResponse:
        effective = dict(self.cookies)
        if cookies:
            effective.update(dict(cookies))
        calls.append(("get", url, effective))

        if url == DEFAULT_BASE_URL:
            return _FakeResponse(url=DEFAULT_BASE_URL, headers={"Expires": "some-date"})
        if url == _SW_PAGE_URL:
            # Simulates another caller (e.g. the GUI's "Forget me" button)
            # clearing the session concurrently, mid-download.
            repo.cookies = None
            return _FakeResponse(content=f'<a href="{_DEVICE_PAGE_URL}">xe121</a>'.encode())
        if url == _DEVICE_PAGE_URL:
            return _FakeResponse(
                content=f'<a href="{_ZIP_URL}">xc120 exploration_server</a>'.encode()
            )
        msg = f"Unexpected GET {url}"
        raise AssertionError(msg)

    def fake_post(
        self: requests.Session,
        url: str,
        data: str | None = None,
        allow_redirects: bool = True,
        cookies: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> _FakeResponse:
        effective = dict(self.cookies)
        if cookies:
            effective.update(dict(cookies))
        calls.append(("post", url, effective))

        if _COOKIE_NAME in effective:
            return _FakeResponse(
                headers={"Content-Disposition": f'attachment; filename="{_FILENAME}"'},
                content=zip_bytes,
            )
        return _FakeResponse(headers={})

    monkeypatch.setattr(requests.Session, "get", fake_get)
    monkeypatch.setattr(requests.Session, "post", fake_post)

    bin_path, version = repo.download(Artifact.XC120_EXPLORATION_SERVER, path=str(tmp_path))

    assert repo.cookies is None, "the race didn't happen as intended"
    assert version == "xc120_exploration_server_v1.2.3"
    assert os.path.exists(bin_path)


def _downloads_row(label: str, form_action: str) -> str:
    """One row of a product page's downloads table, as the developer site renders it"""
    return (
        f"<tr><td>{label}</td><td>Description</td><td>1.0</td><td>2026-07-06</td>"
        '<td><a class="download-button">Download</a></td></tr>'
        f'<tr class="hidden"><td colspan="5"><form class="terms-form" action="{form_action}"'
        ' method="post"><input type="checkbox" name="tc_accepted" value="1" />'
        '<button type="submit" name="tc_submit" value="Download"></button></form></td></tr>'
    )


def test_download_of_algo_bundle_accepts_the_terms_of_its_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    other_url = f"{DEFAULT_BASE_URL}/download/other/?tmstv=1"
    bundle_url = f"{DEFAULT_BASE_URL}/download/bundle/?tmstv=1"
    page = (
        '<table class="downloads-table"><tbody>'
        + _downloads_row("Something else", other_url)
        + _downloads_row("ACCONEER ALGO BUNDLE", bundle_url)
        + "</tbody></table>"
    )
    bundle_bytes = _zip_with_bin("algo/__init__.py", b"")
    posts: list[tuple[str, str | None]] = []

    def fake_get(self: requests.Session, url: str) -> _FakeResponse:
        if url == DEFAULT_BASE_URL:
            return _FakeResponse(url=DEFAULT_BASE_URL, headers={"Expires": "some-date"})
        if url == f"{DEFAULT_BASE_URL}/acconeer-algo-bundle/":
            return _FakeResponse(content=page.encode())
        msg = f"Unexpected GET {url}"
        raise AssertionError(msg)

    def fake_post(
        self: requests.Session,
        url: str,
        data: str | None = None,
        allow_redirects: bool = True,
        headers: dict[str, str] | None = None,
    ) -> _FakeResponse:
        posts.append((url, data))
        return _FakeResponse(
            headers={"Content-Disposition": 'attachment; filename="algo_bundle-1.0.zip"'},
            content=bundle_bytes,
        )

    monkeypatch.setattr(requests.Session, "get", fake_get)
    monkeypatch.setattr(requests.Session, "post", fake_post)
    repo = DevSiteRepository(cookies=requests.cookies.RequestsCookieJar())

    zip_path, version = repo.download(Artifact.ALGO_BUNDLE, path=str(tmp_path))

    assert posts == [(bundle_url, "tc_accepted=1&tc_submit=Download")]
    assert Path(zip_path) == tmp_path / "algo_bundle-1.0.zip"
    assert Path(zip_path).read_bytes() == bundle_bytes
    assert version == "algo_bundle-1.0"
