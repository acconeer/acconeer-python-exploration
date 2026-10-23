# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import sys
from pathlib import Path


_internal_tools_dir = (Path(__file__).parent / ".." / ".." / "internal_tools").resolve()
sys.path.append(_internal_tools_dir.as_posix())

from check_no_imports import check  # noqa: E402


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_plain_import_is_reported_with_its_line(tmp_path: Path) -> None:
    path = _write(tmp_path / "__init__.py", "# header\nimport os\n")

    assert check(path) == [f"{path}:2: imports are not allowed in this file"]


def test_reexport_is_reported(tmp_path: Path) -> None:
    path = _write(tmp_path / "__init__.py", "from ._node import Node as Node\n")

    assert check(path) == [f"{path}:1: imports are not allowed in this file"]


def test_nested_import_is_reported(tmp_path: Path) -> None:
    path = _write(tmp_path / "__init__.py", "def f():\n    import os\n")

    assert check(path) == [f"{path}:2: imports are not allowed in this file"]


def test_file_without_imports_passes(tmp_path: Path) -> None:
    path = _write(tmp_path / "__init__.py", "# Copyright\n# All rights reserved\n")

    assert check(path) == []


def test_missing_file_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "__init__.py"

    assert check(path) == [
        f"{path}: listed in [tool.check_no_imports] in pyproject.toml but does not exist"
    ]
