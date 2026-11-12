# Copyright (c) Acconeer AB, 2026
# All rights reserved
from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path

import pytest
import requests

from acconeer.exptool._artifact_repository import (
    Artifact,
    ArtifactRepositoryError,
    DevSiteRepository,
)
from acconeer.exptool._artifact_repository._algo_bundle import ACCEPTED_VERSION
from acconeer.exptool._artifact_repository._dev_site_repository import (
    _ALGO_BUNDLE_PAGE_PATH,
    DEFAULT_BASE_URL,
)


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


def _downloads_row(label: str, form_action: str, version: str = "1.0") -> str:
    """One row of a product page's downloads table, as the developer site renders it"""
    return (
        f"<tr><td>{label}</td><td>Description</td><td>{version}</td><td>2026-07-06</td>"
        '<td><a class="download-button">Download</a></td></tr>'
        f'<tr class="hidden"><td colspan="5"><form class="terms-form" action="{form_action}"'
        ' method="post"><input type="checkbox" name="tc_accepted" value="1" />'
        '<button type="submit" name="tc_submit" value="Download"></button></form></td></tr>'
    )


_ALGO_BUNDLE_ZIP = _zip_with_bin("algo/__init__.py", b"")


def _serve_algo_bundle_page(
    monkeypatch: pytest.MonkeyPatch, page: str
) -> list[tuple[str, str | None]]:
    """Serves ``page`` as the algo bundle page and ``_ALGO_BUNDLE_ZIP`` behind
    every terms form, returning the URLs and data POSTed to"""
    posts: list[tuple[str, str | None]] = []

    def fake_get(self: requests.Session, url: str) -> _FakeResponse:
        if url == DEFAULT_BASE_URL:
            return _FakeResponse(url=DEFAULT_BASE_URL, headers={"Expires": "some-date"})
        if url == f"{DEFAULT_BASE_URL}{_ALGO_BUNDLE_PAGE_PATH}":
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
            content=_ALGO_BUNDLE_ZIP,
        )

    monkeypatch.setattr(requests.Session, "get", fake_get)
    monkeypatch.setattr(requests.Session, "post", fake_post)
    return posts


def test_download_of_algo_bundle_accepts_the_terms_of_its_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    other_url = f"{DEFAULT_BASE_URL}/download/other/?tmstv=1"
    bundle_url = f"{DEFAULT_BASE_URL}/download/bundle/?tmstv=1"
    page = (
        '<table class="downloads-table"><tbody>'
        + _downloads_row("Something else", other_url)
        + _downloads_row("ACCONEER ALGO BUNDLE", bundle_url, ACCEPTED_VERSION)
        + "</tbody></table>"
    )
    posts = _serve_algo_bundle_page(monkeypatch, page)
    repo = DevSiteRepository(cookies=requests.cookies.RequestsCookieJar())

    zip_path, version = repo.download(Artifact.ALGO_BUNDLE, path=str(tmp_path))

    assert posts == [(bundle_url, "tc_accepted=1&tc_submit=Download")]
    assert Path(zip_path) == tmp_path / "algo_bundle-1.0.zip"
    assert Path(zip_path).read_bytes() == _ALGO_BUNDLE_ZIP
    assert version == "algo_bundle-1.0"


def test_download_of_algo_bundle_refuses_another_version_on_the_site(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    offered = f"{ACCEPTED_VERSION}.1"
    bundle_url = f"{DEFAULT_BASE_URL}/download/bundle/?tmstv=1"
    page = (
        '<table class="downloads-table"><tbody>'
        + _downloads_row("Acconeer Algo Bundle", bundle_url, offered)
        + "</tbody></table>"
    )
    posts = _serve_algo_bundle_page(monkeypatch, page)
    repo = DevSiteRepository(cookies=requests.cookies.RequestsCookieJar())

    with pytest.raises(ArtifactRepositoryError) as exc_info:
        repo.download(Artifact.ALGO_BUNDLE, path=str(tmp_path))

    assert ACCEPTED_VERSION in str(exc_info.value)
    assert offered in str(exc_info.value)
    assert posts == []


def test_download_of_algo_bundle_names_the_et_release_to_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle_url = f"{DEFAULT_BASE_URL}/download/bundle/?tmstv=1"
    page = (
        '<table class="downloads-table"><tbody>'
        + _downloads_row("Acconeer Algo Bundle", bundle_url, "v9.0.0")
        + "</tbody></table>"
    )
    _serve_algo_bundle_page(monkeypatch, page)
    repo = DevSiteRepository(cookies=requests.cookies.RequestsCookieJar())

    with pytest.raises(ArtifactRepositoryError, match=r"acconeer-exptool==9\.0\.0\b"):
        repo.download(Artifact.ALGO_BUNDLE, path=str(tmp_path))


def test_download_of_algo_bundle_accepts_its_version_written_with_a_v(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle_url = f"{DEFAULT_BASE_URL}/download/bundle/?tmstv=1"
    page = (
        '<table class="downloads-table"><tbody>'
        + _downloads_row("Acconeer Algo Bundle", bundle_url, f"v{ACCEPTED_VERSION}")
        + "</tbody></table>"
    )
    posts = _serve_algo_bundle_page(monkeypatch, page)
    repo = DevSiteRepository(cookies=requests.cookies.RequestsCookieJar())

    repo.download(Artifact.ALGO_BUNDLE, path=str(tmp_path))

    assert [url for url, _data in posts] == [bundle_url]


def test_download_of_algo_bundle_picks_its_version_among_others_on_the_site(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    newer_url = f"{DEFAULT_BASE_URL}/download/bundle-newer/?tmstv=1"
    bundle_url = f"{DEFAULT_BASE_URL}/download/bundle/?tmstv=1"
    page = (
        '<table class="downloads-table"><tbody>'
        + _downloads_row("Acconeer Algo Bundle", newer_url, f"{ACCEPTED_VERSION}.1")
        + _downloads_row("Acconeer Algo Bundle", bundle_url, ACCEPTED_VERSION)
        + "</tbody></table>"
    )
    posts = _serve_algo_bundle_page(monkeypatch, page)
    repo = DevSiteRepository(cookies=requests.cookies.RequestsCookieJar())

    repo.download(Artifact.ALGO_BUNDLE, path=str(tmp_path))

    assert [url for url, _data in posts] == [bundle_url]


def test_download_of_algo_bundle_refuses_a_row_without_a_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle_url = f"{DEFAULT_BASE_URL}/download/bundle/?tmstv=1"
    page = (
        '<table class="downloads-table"><tbody>'
        + _downloads_row("Acconeer Algo Bundle", bundle_url, "")
        + "</tbody></table>"
    )
    posts = _serve_algo_bundle_page(monkeypatch, page)
    repo = DevSiteRepository(cookies=requests.cookies.RequestsCookieJar())

    with pytest.raises(ArtifactRepositoryError, match="no algo bundle version"):
        repo.download(Artifact.ALGO_BUNDLE, path=str(tmp_path))

    assert posts == []


def test_download_of_xe212_exploration_server_follows_the_a212_software_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The links and the zip's name are those developer.acconeer.com served
    # on 2026-11-11. The name of the image inside the zip was not seen.
    device_page_url = f"{DEFAULT_BASE_URL}/home/a212-docs-software/xe212/"
    zip_url = f"{DEFAULT_BASE_URL}/download/xe212-exploration-server/?tmstv=1794385663"
    pages = {
        f"{DEFAULT_BASE_URL}/home/a212-docs-software/": (
            f'<a href="{DEFAULT_BASE_URL}/home/a212-docs-software/a212-sdk/">A212 SDK</a>'
            f'<a href="{device_page_url}">XE212</a>'
        ),
        device_page_url: (
            f'<a href="{DEFAULT_BASE_URL}/download/xe212-sdk-a2/?tmstv=1794385663"></a>'
            f'<a href="{zip_url}" class="dlm-tlc__download-xhr"></a>'
        ),
    }
    posts: list[str] = []

    def fake_get(self: requests.Session, url: str) -> _FakeResponse:
        if url == DEFAULT_BASE_URL:
            return _FakeResponse(url=DEFAULT_BASE_URL, headers={"Expires": "some-date"})
        if url in pages:
            return _FakeResponse(content=pages[url].encode())
        msg = f"Unexpected GET {url}"
        raise AssertionError(msg)

    def fake_post(
        self: requests.Session,
        url: str,
        data: str | None = None,
        allow_redirects: bool = True,
        headers: dict[str, str] | None = None,
    ) -> _FakeResponse:
        posts.append(url)
        return _FakeResponse(
            headers={
                "Content-Disposition": 'attachment; filename="acconeer_xe212_exploration_server_a2-v1_2_0.zip"'
            },
            content=_zip_with_bin(
                "acconeer_xe212_exploration_server_a2-v1_2_0.bin", b"binary-data"
            ),
        )

    monkeypatch.setattr(requests.Session, "get", fake_get)
    monkeypatch.setattr(requests.Session, "post", fake_post)
    repo = DevSiteRepository(cookies=requests.cookies.RequestsCookieJar())

    bin_path, version = repo.download(Artifact.XE212_EXPLORATION_SERVER, path=str(tmp_path))

    assert posts == [zip_url]
    assert Path(bin_path) == tmp_path / "acconeer_xe212_exploration_server_a2-v1_2_0.bin"
    assert Path(bin_path).read_bytes() == b"binary-data"
    assert version == "acconeer_xe212_exploration_server_a2-v1_2_0"
