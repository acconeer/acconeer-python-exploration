# Copyright (c) Acconeer AB, 2024-2026
# All rights reserved
from __future__ import annotations

import ast
import enum
import os
import signal
import subprocess
import sys
import uuid
from pathlib import Path

import pytest


def python_files_in_folder(relative_path: str) -> list[str]:
    repo_root = Path(__file__).parent / ".." / ".."
    return [
        example_script.relative_to(repo_root).as_posix()
        for example_script in (repo_root / relative_path).rglob("*.py")
    ]


class ClientOpenAlwaysMockTrue(ast.NodeTransformer):
    """
    Always transforms the source code
        a121.Client.open(<something>)
    into
        a121.Client.open(mock=True)
    """

    @staticmethod
    def is_a121_client_open(node: ast.Call) -> bool:
        return (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Attribute)
            and isinstance(node.func.value.value, ast.Name)
            and node.func.value.value.id == "a121"
            and node.func.value.attr == "Client"
            and node.func.attr == "open"
        )

    def visit_Call(self, node: ast.Call) -> ast.Call:
        if self.is_a121_client_open(node):
            return ast.Call(
                func=node.func,
                args=[],
                keywords=[ast.keyword(arg="mock", value=ast.Constant(value=True))],
            )
        return node


class ModifyFilenameVariableAssignment(ast.NodeTransformer):
    """
    Always transforms the source code
        filename = <literal value, i.e. a constant>
    into
        filename = "<new_filename>"
    """

    def __init__(self, new_filename: str) -> None:
        self._new_filename = new_filename

    def is_filename_assignment(self, node: ast.Assign) -> bool:
        return (
            len(node.targets) == 1
            and node.targets[0].id == "filename"
            and isinstance(node.value, ast.Constant)
        )

    def visit_Assign(self, node: ast.Call) -> ast.Call:
        if self.is_filename_assignment(node):
            return ast.Assign(
                targets=[ast.Name(id="filename", ctx=ast.Store())],
                value=ast.Constant(value=self._new_filename),
            )
        return node


class AstModifications(enum.Flag):
    CLIENT_OPEN = enum.auto()
    FILENAME_VARIABLE = enum.auto()

    def create_modified_file(
        self,
        input_script_path: str,
        output_script_path: str,
        new_filename: str,
    ) -> None:
        tree = ast.parse(Path(input_script_path).read_text())

        if AstModifications.CLIENT_OPEN in self:
            tree = ClientOpenAlwaysMockTrue().visit(tree)

        if AstModifications.FILENAME_VARIABLE in self:
            tree = ModifyFilenameVariableAssignment(new_filename).visit(tree)

        tree = ast.fix_missing_locations(tree)
        output_script_path.write_text(ast.unparse(tree))


_EXAMPLE_ARGUMENTS: dict[str, list[str]] = {
    "examples/a121/record_data/with_cli.py": [
        "--mock",
        "--output-file",
        "{tmp_path}/with_cli_output.h5",
        "--num-frames",
        "10",
    ],
    "examples/a121/extended_config.py": ["--mock"],
    "examples/a121/load_record.py": ["tests/processing/a121/data_files/recorded_data/input.h5"],
    "examples/a121/plot.py": ["--mock"],
    "examples/a121/post_process_sparse_iq.py": [
        "tests/processing/a121/data_files/recorded_data/input.h5"
    ],
    "examples/a121/reuse_calibration.py": ["--mock"],
    "examples/a121/subsweeps.py": ["--mock"],
    "examples/a121/algo/bilateration/bilaterator.py": ["--mock"],
    "examples/a121/algo/breathing/breathing_with_gui.py": ["--mock"],
    "examples/a121/algo/breathing/breathing.py": ["--mock"],
    "examples/a121/algo/cargo/example_app.py": ["--mock"],
    "examples/a121/algo/distance/detector.py": ["--mock"],
    "examples/a121/algo/distance/processor.py": ["--mock"],
    "examples/a121/algo/distance/post_process_distance_result.py": [
        "--input-file",
        "tests/processing/a121/data_files/recorded_data/distance-5to10.h5",
    ],
    "examples/a121/algo/obstacle/detector.py": ["--mock"],
    "examples/a121/algo/parking/parking.py": ["--mock"],
    "examples/a121/algo/phase_tracking/phase_tracking.py": ["--mock"],
    "examples/a121/algo/presence/detector.py": ["--mock"],
    "examples/a121/algo/presence/processor.py": ["--mock"],
    "examples/a121/algo/smart_presence/processor.py": ["--mock"],
    "examples/a121/algo/smart_presence/ref_app.py": ["--mock"],
    "examples/a121/algo/sparse_iq/sparse_iq.py": ["--mock"],
    "examples/a121/algo/speed/detector.py": ["--mock"],
    "examples/a121/algo/speed/processor.py": ["--mock"],
    "examples/a121/algo/surface_velocity/example_app.py": ["--mock"],
    "examples/a121/algo/surface_velocity/processor.py": ["--mock"],
    "examples/a121/algo/tank_level/tank_level_with_gui.py": ["--mock"],
    "examples/a121/algo/tank_level/tank_level.py": ["--mock"],
    "examples/a121/algo/touchless_button/processor.py": ["--mock"],
    "examples/a121/algo/vibration/example_app.py": ["--mock"],
    "examples/a121/algo/vibration/processor.py": ["--mock"],
    "examples/a121/algo/waste_level/processor.py": ["--mock"],
}

_EXAMPLE_MODIFICATIONS: dict[str, AstModifications] = {
    "examples/a121/basic.py": AstModifications.CLIENT_OPEN,
    "examples/a121/record_data/barebones.py": (
        AstModifications.CLIENT_OPEN | AstModifications.FILENAME_VARIABLE
    ),
    "examples/a121/algo/hand_motion/hand_motion_example_app.py": AstModifications.CLIENT_OPEN,
}

_EXAMPLES = sorted(_EXAMPLE_ARGUMENTS.keys() | _EXAMPLE_MODIFICATIONS.keys())


def test_every_example_is_run_once() -> None:
    assert sorted(python_files_in_folder("examples/a121")) == _EXAMPLES
    assert not _EXAMPLE_ARGUMENTS.keys() & _EXAMPLE_MODIFICATIONS.keys()


@pytest.mark.parametrize("example_script", _EXAMPLES)
def test_a121_examples(example_script: str, tmp_path: Path) -> None:
    env = {"QT_QPA_PLATFORM": "offscreen", **os.environ}
    if (example_arguments := _EXAMPLE_ARGUMENTS.get(example_script)) is not None:
        args = [arg.format(tmp_path=tmp_path.as_posix()) for arg in example_arguments]
        p = subprocess.Popen([sys.executable, example_script, *args], env=env)
    else:
        new_filename = (tmp_path / f"{uuid.uuid4()}.h5").as_posix()
        modified_example_script_path = tmp_path / (Path(example_script).name)

        _EXAMPLE_MODIFICATIONS[example_script].create_modified_file(
            input_script_path=example_script,
            output_script_path=modified_example_script_path,
            new_filename=new_filename,
        )

        p = subprocess.Popen([sys.executable, modified_example_script_path], env=env)

    start_grace_period_s = 3
    interrupt_timeout_s = 3
    kill_timeout_s = 1

    # The example is non-interactive and without while-loop
    # This is also where we whould find examples that don't run
    try:
        returncode = p.wait(timeout=start_grace_period_s)
    except subprocess.TimeoutExpired:
        pass
    else:
        assert returncode == 0
        return

    # The example is long-running and expects the user to interrupt it.
    try:
        p.send_signal(signal.SIGINT)
        returncode = p.wait(timeout=interrupt_timeout_s)
    except subprocess.TimeoutExpired:
        pass
    else:
        assert returncode in [0, -signal.SIGINT]
        return

    # The example didn't clean-up properly. Kill it.
    try:
        p.send_signal(signal.SIGKILL)
        returncode = p.wait(timeout=kill_timeout_s)
    except subprocess.TimeoutExpired:
        pytest.fail(
            f"{example_script!r} did not exit within {kill_timeout_s} seconds after kill signal."
        )
    else:
        assert returncode in [0, 1, -signal.SIGKILL]
        return
