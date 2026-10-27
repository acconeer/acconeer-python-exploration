# Copyright (c) Acconeer AB, 2024-2026
# All rights reserved
from __future__ import annotations

import ast
import contextlib
import enum
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

import attrs
import pytest

from acconeer.exptool.utils import ExampleInterruptHandler


type StartExample = Callable[[list[str]], tuple[subprocess.Popen[str], threading.Event]]


@pytest.fixture
def start_example() -> Iterator[StartExample]:
    """Starts examples, each with an event set once it prompts for Ctrl-C."""
    started: list[tuple[subprocess.Popen[str], threading.Thread]] = []

    def start(args: list[str]) -> tuple[subprocess.Popen[str], threading.Event]:
        p = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            text=True,
            # Its own session lets cleanup reach the example's children, e.g. a plotting process.
            start_new_session=True,
            # Headless, so a closing plt.show() returns rather than waits on its window.
            env={
                "QT_QPA_PLATFORM": "offscreen",
                **os.environ,
                "PYTHONUNBUFFERED": "1",
                "MPLBACKEND": "Agg",
            },
        )
        assert p.stdout is not None
        stdout = p.stdout
        ready = threading.Event()

        def forward_output() -> None:
            for line in stdout:
                sys.stdout.write(line)
                # Printed once the example's handler is set, so Ctrl-C is safe from then on.
                if ExampleInterruptHandler.PROMPT in line:
                    ready.set()

        forwarder = threading.Thread(target=forward_output, daemon=True)
        forwarder.start()
        started.append((p, forwarder))
        return p, ready

    yield start

    for p, forwarder in started:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(p.pid, signal.SIGKILL)
        # Joined so the example's last output lands in this test's report.
        forwarder.join(timeout=5)
        if not forwarder.is_alive() and p.stdout is not None:
            p.stdout.close()


def python_files_in_folder(relative_path: str) -> list[str]:
    repo_root = Path(__file__).parent / ".." / ".."
    return [
        example_script.relative_to(repo_root).as_posix()
        for example_script in (repo_root / relative_path).rglob("*.py")
    ]


class ClientOpenAlwaysMockTrue(ast.NodeTransformer):
    """
    Always transforms the source code
        (a121|a2).Client.open(<something>)
    into
        (a121|a2).Client.open(mock=True)
    """

    @staticmethod
    def is_a121_or_a2_client_open(node: ast.Call) -> bool:
        return (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Attribute)
            and isinstance(node.func.value.value, ast.Name)
            and node.func.value.value.id in ["a121", "a2"]
            and node.func.value.attr == "Client"
            and node.func.attr == "open"
        )

    def visit_Call(self, node: ast.Call) -> ast.Call:
        if self.is_a121_or_a2_client_open(node):
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


@attrs.frozen(kw_only=True)
class ExampleRun:
    args: tuple[str, ...] = ()
    modifications: AstModifications = AstModifications(0)


_EXAMPLES: dict[str, ExampleRun] = {
    "examples/a121/record_data/barebones.py": ExampleRun(
        modifications=AstModifications.CLIENT_OPEN | AstModifications.FILENAME_VARIABLE
    ),
    "examples/a121/record_data/with_cli.py": ExampleRun(
        args=("--mock", "--output-file", "{tmp_path}/with_cli_output.h5", "--num-frames", "10")
    ),
    "examples/a121/basic.py": ExampleRun(modifications=AstModifications.CLIENT_OPEN),
    "examples/a121/extended_config.py": ExampleRun(args=("--mock",)),
    "examples/a121/load_record.py": ExampleRun(
        args=("tests/processing/a121/data_files/recorded_data/input.h5",)
    ),
    "examples/a121/plot.py": ExampleRun(args=("--mock",)),
    "examples/a121/post_process_sparse_iq.py": ExampleRun(
        args=("tests/processing/a121/data_files/recorded_data/input.h5",)
    ),
    "examples/a121/reuse_calibration.py": ExampleRun(args=("--mock",)),
    "examples/a121/subsweeps.py": ExampleRun(args=("--mock",)),
    "examples/a121/algo/bilateration/bilaterator.py": ExampleRun(args=("--mock",)),
    "examples/a121/algo/breathing/breathing_with_gui.py": ExampleRun(args=("--mock",)),
    "examples/a121/algo/breathing/breathing.py": ExampleRun(args=("--mock",)),
    "examples/a121/algo/cargo/example_app.py": ExampleRun(args=("--mock",)),
    "examples/a121/algo/distance/detector.py": ExampleRun(args=("--mock",)),
    "examples/a121/algo/distance/processor.py": ExampleRun(args=("--mock",)),
    "examples/a121/algo/distance/post_process_distance_result.py": ExampleRun(
        args=("--input-file", "tests/processing/a121/data_files/recorded_data/distance-5to10.h5")
    ),
    "examples/a121/algo/hand_motion/hand_motion_example_app.py": ExampleRun(
        modifications=AstModifications.CLIENT_OPEN
    ),
    "examples/a121/algo/obstacle/detector.py": ExampleRun(args=("--mock",)),
    "examples/a121/algo/parking/parking.py": ExampleRun(args=("--mock",)),
    "examples/a121/algo/phase_tracking/phase_tracking.py": ExampleRun(args=("--mock",)),
    "examples/a121/algo/presence/detector.py": ExampleRun(args=("--mock",)),
    "examples/a121/algo/presence/processor.py": ExampleRun(args=("--mock",)),
    "examples/a121/algo/smart_presence/processor.py": ExampleRun(args=("--mock",)),
    "examples/a121/algo/smart_presence/ref_app.py": ExampleRun(args=("--mock",)),
    "examples/a121/algo/sparse_iq/sparse_iq.py": ExampleRun(args=("--mock",)),
    "examples/a121/algo/speed/detector.py": ExampleRun(args=("--mock",)),
    "examples/a121/algo/speed/processor.py": ExampleRun(args=("--mock",)),
    "examples/a121/algo/surface_velocity/example_app.py": ExampleRun(args=("--mock",)),
    "examples/a121/algo/surface_velocity/processor.py": ExampleRun(args=("--mock",)),
    "examples/a121/algo/tank_level/tank_level_with_gui.py": ExampleRun(args=("--mock",)),
    "examples/a121/algo/tank_level/tank_level.py": ExampleRun(args=("--mock",)),
    "examples/a121/algo/touchless_button/processor.py": ExampleRun(args=("--mock",)),
    "examples/a121/algo/vibration/example_app.py": ExampleRun(args=("--mock",)),
    "examples/a121/algo/vibration/processor.py": ExampleRun(args=("--mock",)),
    "examples/a121/algo/waste_level/processor.py": ExampleRun(args=("--mock",)),
    "examples/a2/load_data_with_antenna_masks_and_sub_sampling.py": ExampleRun(
        args=("--input-file", "tests/processing/a2/data_files/recorded_data/small_sparse_iq.h5")
    ),
    "examples/a2/multiple_modules.py": ExampleRun(modifications=AstModifications.CLIENT_OPEN),
    "examples/a2/reuse_calibration.py": ExampleRun(modifications=AstModifications.CLIENT_OPEN),
    "examples/a2/record_data/barebones.py": ExampleRun(
        modifications=AstModifications.CLIENT_OPEN | AstModifications.FILENAME_VARIABLE
    ),
    "examples/a2/algo/heatmap/heatmap_processor.py": ExampleRun(
        modifications=AstModifications.CLIENT_OPEN
    ),
    "examples/a2/algo/heatmap/heatmap_visualization.py": ExampleRun(
        args=("--input-file", "tests/processing/a2/data_files/recorded_data/small_sparse_iq.h5")
    ),
}


def test_every_example_is_run() -> None:
    examples = python_files_in_folder("examples/a121") + python_files_in_folder("examples/a2")
    assert sorted(examples) == sorted(_EXAMPLES)


def _example_command(example_script: str, run: ExampleRun, tmp_path: Path) -> list[str]:
    script = Path(example_script)
    if run.modifications:
        script = tmp_path / script.name
        run.modifications.create_modified_file(
            input_script_path=example_script,
            output_script_path=script,
            new_filename=(tmp_path / f"{uuid.uuid4()}.h5").as_posix(),
        )

    args = [arg.format(tmp_path=tmp_path.as_posix()) for arg in run.args]
    return [sys.executable, str(script), *args]


def test_example_command_modifies_the_script_and_passes_arguments(tmp_path: Path) -> None:
    example_script = tmp_path / "examples" / "example.py"
    example_script.parent.mkdir()
    example_script.write_text('client = a121.Client.open(ip_address="192.168.0.1")\n')
    run = ExampleRun(
        args=("--output-file", "{tmp_path}/out.h5"), modifications=AstModifications.CLIENT_OPEN
    )

    command = _example_command(example_script.as_posix(), run, tmp_path)

    modified_script = tmp_path / "example.py"
    assert command == [
        sys.executable,
        str(modified_script),
        "--output-file",
        f"{tmp_path.as_posix()}/out.h5",
    ]
    assert modified_script.read_text().strip() == "client = a121.Client.open(mock=True)"


@pytest.mark.parametrize("example_script", sorted(_EXAMPLES))
def test_examples(example_script: str, tmp_path: Path, start_example: StartExample) -> None:
    command = _example_command(example_script, _EXAMPLES[example_script], tmp_path)
    p, ready = start_example(command)

    startup_timeout_s = 60
    # Generous, as a loaded machine can take seconds to shut an example down.
    interrupt_timeout_s = 30

    # A SIGINT during imports can be lost or crash the example, and a slow machine can
    # spend seconds on them.
    deadline = time.monotonic() + startup_timeout_s
    while not ready.wait(timeout=0.1):
        if (returncode := p.poll()) is not None:
            # The example is non-interactive and without while-loop
            # This is also where we would find examples that don't run
            assert returncode == 0
            return
        if time.monotonic() > deadline:
            pytest.fail(
                f"{example_script!r} neither exited nor printed"
                f" {ExampleInterruptHandler.PROMPT!r} within {startup_timeout_s} seconds."
            )

    # The example runs until Ctrl-C, which a terminal sends to its whole process group.
    os.killpg(p.pid, signal.SIGINT)
    try:
        returncode = p.wait(timeout=interrupt_timeout_s)
    except subprocess.TimeoutExpired:
        pytest.fail(
            f"{example_script!r} did not exit within {interrupt_timeout_s} seconds of Ctrl-C."
        )
    assert returncode in [0, -signal.SIGINT]
