# Copyright (c) Acconeer AB, 2026
# All rights reserved

import subprocess as sp
from pathlib import Path


def test_purge_cache_does_not_remove_data_dir_override(tmp_path: Path) -> None:
    """The --data-dir can turn ET into an rm command.
    Let's protect our users by not allowing deletion of the given --data-dir.
    """
    phony_data_dir = tmp_path / "a_directory"
    phony_data_dir.mkdir()

    sp.check_call(
        [
            "python",
            "-m",
            "acconeer.exptool.app.new",
            "--purge-cache",
            "--data-dir",
            phony_data_dir,
        ]
    )

    assert phony_data_dir.exists()
