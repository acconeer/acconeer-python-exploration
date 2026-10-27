# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import sys
from pathlib import Path

import pytest


_cwd = Path(__file__).parent
_docs_dir = (_cwd / ".." / ".." / "docs").resolve()
sys.path.append(_docs_dir.as_posix())

from check_html_redirects import check_redirect, main  # noqa: E402


_ANCHOR = "radar-loop-gain-rlg"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_tree(
    tmp_path: Path, *, target_exists: bool, anchor_exists: bool
) -> tuple[Path, Path, Path]:
    """
    Build a minimal docs + build tree and return (source_rst, build_dir, docs_root).

    Mirrors how check_redirect() resolves paths: the redirect page lives under the docs
    root and its built counterpart mirrors that tree; the redirect target is resolved
    relative to the built page's location.
    """
    docs_root = tmp_path / "docs"
    build_dir = tmp_path / "build"

    # Source redirect page: docs/datasheet/page.rst
    source_rst = docs_root / "datasheet" / "page.rst"
    _write(
        source_rst,
        f"<script>window.location.replace('../target.html#{_ANCHOR}');</script>\n",
    )

    # Built redirect page must exist: build/datasheet/page.html
    _write(build_dir / "datasheet" / "page.html", "<html><body>redirect</body></html>")

    # Built target page: build/target.html
    if target_exists:
        anchor_html = f"<h1 id='{_ANCHOR}'>RLG</h1>" if anchor_exists else "<h1>Other</h1>"
        _write(build_dir / "target.html", f"<html><body>{anchor_html}</body></html>")

    return source_rst, build_dir, docs_root


def test_catches_broken_anchor(tmp_path: Path) -> None:
    """A redirect to an anchor that does not exist in the target must be reported."""
    source_rst, build_dir, docs_root = _make_tree(
        tmp_path, target_exists=True, anchor_exists=False
    )

    errors = check_redirect(source_rst, build_dir, docs_root)

    assert errors, "expected the missing anchor to be reported"
    assert any(_ANCHOR in error for error in errors)


def test_catches_missing_target_file(tmp_path: Path) -> None:
    """A redirect whose target HTML file does not exist must be reported."""
    source_rst, build_dir, docs_root = _make_tree(
        tmp_path, target_exists=False, anchor_exists=False
    )

    errors = check_redirect(source_rst, build_dir, docs_root)

    assert errors, "expected the missing target file to be reported"
    assert any("target file does not exist" in error for error in errors)


def test_passes_for_valid_redirect(tmp_path: Path) -> None:
    """A redirect to an existing target file and anchor must produce no errors."""
    source_rst, build_dir, docs_root = _make_tree(tmp_path, target_exists=True, anchor_exists=True)

    assert check_redirect(source_rst, build_dir, docs_root) == []


def test_main_exits_nonzero_on_broken_redirect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: the CLI must exit non-zero when a redirect is broken."""
    _, build_dir, docs_root = _make_tree(tmp_path, target_exists=True, anchor_exists=False)
    source_dir = docs_root / "datasheet"

    monkeypatch.setattr(
        sys, "argv", ["check_html_redirects.py", str(build_dir), "--source-dir", str(source_dir)]
    )

    with pytest.raises(SystemExit) as excinfo:
        main()

    assert excinfo.value.code != 0


def test_main_exits_zero_on_valid_redirect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end control: the CLI must exit 0 when all redirects are valid."""
    _, build_dir, docs_root = _make_tree(tmp_path, target_exists=True, anchor_exists=True)
    source_dir = docs_root / "datasheet"

    monkeypatch.setattr(
        sys, "argv", ["check_html_redirects.py", str(build_dir), "--source-dir", str(source_dir)]
    )

    with pytest.raises(SystemExit) as excinfo:
        main()

    assert excinfo.value.code == 0
