# Copyright (c) Acconeer AB, 2026
# All rights reserved
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from internal_tools.check_released_algo_bundle import (
    ReleaseGateError,
    check_released_algo_bundle,
)

from acconeer.exptool._artifact_repository import Artifact, LoginRequiredError


class _FakeDevSite:
    def __init__(self, zip_content: bytes = b"bundle", error: Exception | None = None) -> None:
        self.zip_content = zip_content
        self.error = error

    def download(self, artifact: Artifact, path: str) -> tuple[str, str]:
        assert artifact is Artifact.MODULE_BUNDLE
        if self.error is not None:
            raise self.error
        zip_path = Path(path) / "bundle.zip"
        zip_path.write_bytes(self.zip_content)
        return str(zip_path), "v1.0.0"


def test_passes_when_the_developer_site_serves_the_accepted_algo_bundle(
    tmp_path: Path,
) -> None:
    accepted = hashlib.sha256(b"accepted bundle").hexdigest()

    check_released_algo_bundle(
        _FakeDevSite(zip_content=b"accepted bundle"), frozenset({accepted}), tmp_path
    )


def test_fails_when_the_release_pins_no_algo_bundle(tmp_path: Path) -> None:
    with pytest.raises(ReleaseGateError, match="pins no algo bundle"):
        check_released_algo_bundle(_FakeDevSite(), frozenset(), tmp_path)


def test_fails_when_the_developer_site_serves_another_algo_bundle(tmp_path: Path) -> None:
    accepted = hashlib.sha256(b"accepted bundle").hexdigest()
    served = hashlib.sha256(b"other bundle").hexdigest()

    with pytest.raises(ReleaseGateError, match=f"{served}.*{accepted}"):
        check_released_algo_bundle(
            _FakeDevSite(zip_content=b"other bundle"), frozenset({accepted}), tmp_path
        )


def test_fails_when_et_cannot_download_the_algo_bundle_yet(tmp_path: Path) -> None:
    with pytest.raises(ReleaseGateError, match="can't download the algo bundle"):
        check_released_algo_bundle(
            _FakeDevSite(error=NotImplementedError()), frozenset({"digest"}), tmp_path
        )


def test_fails_when_the_developer_site_rejects_the_login(tmp_path: Path) -> None:
    with pytest.raises(ReleaseGateError, match="rejected the login. Check credentials"):
        check_released_algo_bundle(
            _FakeDevSite(error=LoginRequiredError()), frozenset({"digest"}), tmp_path
        )
