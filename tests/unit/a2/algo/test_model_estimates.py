# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import ast
from pathlib import Path

import acconeer.exptool.a2.algo as algo


_MODEL_PACKAGE = "acconeer.exptool.a2.model"
_ALLOWED_IMPORTER = Path("_model_estimates.py")


def _imported_modules(path: Path, package: str) -> set[str]:
    """Absolute names of every module, and every name imported from a module,
    in ``path``.

    :param package: Dotted name of the package containing ``path``, used to
        resolve relative imports.
    """
    package_parts = package.split(".")
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base_parts = package_parts[: len(package_parts) - node.level + 1] if node.level else []
            module = ".".join([*base_parts, *([node.module] if node.module else [])])
            modules.add(module)
            modules.update(f"{module}.{alias.name}" for alias in node.names)
    return modules


def _model_importers(root: Path, package: str) -> list[str]:
    """Files under ``root`` (the directory of ``package``), other than
    ``_ALLOWED_IMPORTER``, that import from ``_MODEL_PACKAGE``."""
    offenders = []
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        if relative == _ALLOWED_IMPORTER:
            continue
        file_package = ".".join([package, *relative.parent.parts])
        if any(
            module == _MODEL_PACKAGE or module.startswith(f"{_MODEL_PACKAGE}.")
            for module in _imported_modules(path, file_package)
        ):
            offenders.append(relative.as_posix())
    return offenders


def test_only_model_estimates_imports_a2_model():
    offenders = _model_importers(Path(algo.__file__).parent, algo.__name__)
    assert not offenders, (
        f"{offenders} import {_MODEL_PACKAGE}. Code in {algo.__name__} must go "
        f"through {algo.__name__}._model_estimates instead."
    )


def test_model_importers_detects_absolute_and_relative_imports(tmp_path):
    (tmp_path / "sub").mkdir()
    sources = {
        "absolute.py": "from acconeer.exptool.a2.model import power\n",
        "plain.py": "import acconeer.exptool.a2.model.power as a2_power\n",
        "package_name.py": "from acconeer.exptool.a2 import model\n",
        "relative.py": "from ..model import power\n",
        "sub/relative_deep.py": "from ...model.power import frame_active\n",
        "in_function.py": "def f():\n    from acconeer.exptool.a2.model import memory\n",
        "unrelated.py": "from acconeer.exptool.a2.algo import _utils\nimport acconeer.exptool.a2\n",
        "_model_estimates.py": "from acconeer.exptool.a2.model import power\n",
    }
    for name, source in sources.items():
        (tmp_path / name).write_text(source, encoding="utf-8")

    assert _model_importers(tmp_path, "acconeer.exptool.a2.algo") == [
        "absolute.py",
        "in_function.py",
        "package_name.py",
        "plain.py",
        "relative.py",
        "sub/relative_deep.py",
    ]
