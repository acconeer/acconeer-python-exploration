# Copyright (c) Acconeer AB, 2026
# All rights reserved

import ast
import sys
import tomllib as toml
from pathlib import Path


def main() -> bool:
    with open("pyproject.toml", "rb") as fp:
        config = toml.load(fp)["tool"]["check_no_imports"]

    errors = [error for filename in config["include"] for error in check(Path(filename))]
    for error in errors:
        print(error)

    return bool(errors)


def check(path: Path) -> list[str]:
    if not path.exists():
        return [f"{path}: listed in [tool.check_no_imports] in pyproject.toml but does not exist"]

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        f"{path}:{node.lineno}: imports are not allowed in this file"
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]


if __name__ == "__main__":
    sys.exit(int(main()))
