# Copyright (c) Acconeer AB, 2024-2026
# All rights reserved

import subprocess as sp
import time
import typing as t
from pathlib import Path

import pytest


def worker_id_to_tcp_port(worker_id: str, tcp_port_base: int) -> int:
    if worker_id == "master":
        return tcp_port_base
    elif worker_id.startswith("gw"):  # are on the format "gw\d+"
        offset = int(worker_id[2:])
        return tcp_port_base + (offset + 1)
    else:
        msg = f"Unexpected {worker_id=}"
        raise ValueError(msg)


@pytest.fixture(scope="session")
def worker_tcp_port(worker_id: str) -> int:
    """Returns a unique tcp port for each pytest-xdist worker to use for its Exploration Server"""
    return worker_id_to_tcp_port(worker_id, tcp_port_base=6110)


@pytest.fixture(scope="session")
def fuzzing_a121_worker_tcp_port(worker_id: int) -> int:
    """Returns a unique tcp port for each pytest-xdist worker to use for its session-scoped, fuzzing Exploration Server"""
    return worker_id_to_tcp_port(worker_id, tcp_port_base=16110)


@pytest.fixture(scope="session")
def fuzzing_a121_exploration_server(
    fuzzing_a121_worker_tcp_port: int,
    a121_exploration_server_path: Path,
    tmp_path_factory: pytest.TempPathFactory,
) -> t.Iterator[None]:
    # NOTE!
    # This server might be running at the same time as the servers managed by the
    # "a121_exploration_server" fixture
    yield from exploration_server_process_fixture(
        fuzzing_a121_worker_tcp_port,
        a121_exploration_server_path,
        tmp_path_factory.mktemp("fuzzing_server"),
    )


def exploration_server_process_fixture(
    tcp_port: int,
    server_binary_path: Path,
    log_dir: Path,
    startup_timeout_s: float = 60,
    stop_timeout_s: float = 5,
) -> t.Iterator[None]:
    args = [server_binary_path.as_posix(), "--port", str(tcp_port)]
    env = {"ACC_MOCK_TEST_PATTERN": "1"}

    # A file, unlike a pipe, never fills up and blocks the server.
    log_path = log_dir / "server.log"
    with (
        log_path.open("w") as log_file,
        sp.Popen(args, stdout=log_file, stderr=sp.STDOUT, env=env) as server_process,
    ):
        try:
            deadline = time.monotonic() + startup_timeout_s
            while "waiting" not in log_path.read_text().lower():
                if time.monotonic() > deadline:
                    pytest.fail("Server did not start listening in time")
                try:
                    server_process.wait(timeout=0.01)
                except sp.TimeoutExpired:
                    continue
                pytest.fail("Server exited prematurely")

            yield  # give control to test function
        finally:
            server_process.terminate()
            try:
                server_process.wait(timeout=stop_timeout_s)
            except sp.TimeoutExpired:
                server_process.kill()
            print(log_path.read_text(), end="")


@pytest.fixture(scope="function")
def a121_exploration_server(
    worker_tcp_port: int, a121_exploration_server_path: Path, tmp_path: Path
) -> t.Iterator[None]:
    yield from exploration_server_process_fixture(
        worker_tcp_port, a121_exploration_server_path, tmp_path
    )


@pytest.fixture(scope="function")
def a111_exploration_server(
    worker_tcp_port: int, a111_exploration_server_path: Path, tmp_path: Path
) -> t.Iterator[None]:
    yield from exploration_server_process_fixture(
        worker_tcp_port, a111_exploration_server_path, tmp_path
    )
