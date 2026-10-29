# Copyright (c) Acconeer AB, 2026
# All rights reserved

"""Fails a release build unless the developer site serves the accepted algo bundle."""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from collections.abc import Collection
from pathlib import Path

from acconeer.exptool._artifact_repository import (
    ACCEPTED_DIGESTS,
    Artifact,
    ArtifactRepository,
    DevSiteRepository,
    LoginRequiredError,
)


class ReleaseGateError(Exception):
    pass


def check_released_algo_bundle(
    repository: ArtifactRepository, accepted_digests: Collection[str], download_dir: Path
) -> None:
    if not accepted_digests:
        msg = "This release pins no algo bundle. Pin the accepted bundle's SHA-256 before tagging."
        raise ReleaseGateError(msg)

    try:
        zip_path, _version = repository.download(Artifact.ALGO_BUNDLE, str(download_dir))
    except NotImplementedError as e:
        msg = (
            "ET can't download the algo bundle from the developer site yet. "
            "Implement it before tagging a release."
        )
        raise ReleaseGateError(msg) from e
    except LoginRequiredError as e:
        msg = "The developer site rejected the login. Check credentials."
        raise ReleaseGateError(msg) from e
    digest = hashlib.sha256(Path(zip_path).read_bytes()).hexdigest()
    if digest not in accepted_digests:
        msg = (
            f"The developer site serves an algo bundle with SHA-256 {digest}; "
            f"this release accepts {', '.join(sorted(accepted_digests))}. "
            "Upload the accepted bundle, then rebuild this tag."
        )
        raise ReleaseGateError(msg)


def main() -> None:
    username = os.getenv("DEV_USERNAME")
    password = os.getenv("DEV_PASSWORD")
    if username is None or password is None:
        sys.exit("Set DEV_USERNAME and DEV_PASSWORD to a developer site account.")

    repository = DevSiteRepository(cookies=None)
    repository.login(username, password)
    with tempfile.TemporaryDirectory() as download_dir:
        try:
            check_released_algo_bundle(repository, ACCEPTED_DIGESTS, Path(download_dir))
        except ReleaseGateError as e:
            sys.exit(str(e))
    print("The developer site serves the accepted algo bundle.")


if __name__ == "__main__":
    main()
