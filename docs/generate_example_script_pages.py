# Copyright (c) Acconeer AB, 2024
# All rights reserved
import argparse
from pathlib import Path


DESCRIPTION = """
Generate non-A111 Example Script pages
"""

AUTOGEN_COMMENT = ".. This document was automatically generated with the script 'docs/generate_example_script_pages.py'"


def script_docpage_contents(docpage_path: Path, et_root: Path, script_path: Path) -> str:
    header_line = "#" * len(str(script_path))
    include_path = _path_to_ancestor(docpage_path.parent, et_root) / script_path
    return f"""{AUTOGEN_COMMENT}

{header_line}
{str(script_path)}
{header_line}

.. literalinclude:: {include_path}
   :linenos:

View this example on GitHub: `<https://github.com/acconeer/acconeer-python-exploration/tree/master/{script_path}>`_
"""


def index_docpage_contents(category: str) -> str:
    title = category.replace("_", " ").title().replace("Api", "API") + " Example Scripts"
    header_line = "#" * len(str(title))
    return f"""{AUTOGEN_COMMENT}

{header_line}
{title}
{header_line}

.. toctree::
   :maxdepth: 1
   :glob:

   *
"""


def document_include_path(document_dir_path: Path, et_root: Path, script_path: Path) -> Path:
    """The path that will be the argument to a ..literalinclude:: directive"""
    return _path_to_ancestor(document_dir_path, et_root) / script_path


def _path_to_ancestor(path: Path, parent: Path) -> Path:
    assert path.is_dir() and parent.is_dir()
    return Path("./") if path == parent else _path_to_ancestor(path.parent, parent) / ".."


def example_script_category(example_script_path: Path) -> str:
    """Determine the category of a script, given its path"""
    parts = list(example_script_path.parts)

    if "algo" in parts:
        return parts[parts.index("algo") + 1]
    elif "app" in parts:
        return "app"
    else:
        return "python_api"


def example_script_docpage_path(example_script_path: Path) -> Path:
    """Return a path, relative to 'docpages_root', where a script's docpage should be located"""

    dst_dir = Path(example_script_category(example_script_path))
    return dst_dir / str(example_script_path.with_suffix(".rst")).replace("/", "-")


def main() -> None:
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument(
        "--et-root",
        type=Path,
        default=".",
        help="ET repo root. The directory where pyproject.toml lives.",
    )
    parser.add_argument("verb", choices={"check", "generate"})
    parser.add_argument(
        "--example-script-output-folder",
        type=Path,
        default=Path("docs/exploration_tool/example_scripts"),
        help="A path relative to 'et_root', under which example script docpages should be placed.",
    )

    args = parser.parse_args()

    if not (args.et_root / "pyproject.toml").exists():
        print(f"The directory {args.et_root} does not contain a 'pyproject.toml' file")
        exit(1)

    docpages_root = args.et_root / args.example_script_output_folder
    example_scripts = list(args.et_root.glob("examples/**/*.py"))

    category_indexes = {
        docpages_root / example_script_category(script) / "index.rst" for script in example_scripts
    }
    missing_category_indexes = {path for path in category_indexes if not path.exists()}

    path_mapping = {
        script_path: docpages_root / example_script_docpage_path(script_path)
        for script_path in example_scripts
        if "a111" not in script_path.parts
    }
    missing_docpages = {
        script_path: docpage_path
        for script_path, docpage_path in path_mapping.items()
        if not docpage_path.exists()
    }

    if args.verb == "check":
        if missing_docpages:
            print("Missing example script docpages for examples:")
            for path in missing_docpages:
                print(" -", path)
            exit(1)
        if missing_category_indexes:
            print("Missing category index pages:")
            for path in missing_category_indexes:
                print(" -", path)
            exit(1)
        print("All examples script docpages are up to date!")
        exit(0)
    elif args.verb == "generate":
        for index_path in missing_category_indexes:
            index_path.parent.mkdir(parents=True, exist_ok=True)
            print(f"Writing {index_path}")
            index_path.write_text(index_docpage_contents(index_path.parent.name))
        for script_path, docpage_path in missing_docpages.items():
            docpage_path.parent.mkdir(parents=True, exist_ok=True)
            print(f"Writing {script_path} to {docpage_path}")
            docpage_path.write_text(
                script_docpage_contents(docpage_path, args.et_root, script_path)
            )
        print("All examples script docpages are up to date!")
        exit(0)
    else:
        print(f"Unknown verb {args.verb}.")
        exit(1)


if __name__ == "__main__":
    main()
