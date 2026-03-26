# Copyright (c) Acconeer AB, 2024-2026
# All rights reserved

import subprocess as sp
import typing as t
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def worker_tcp_port(worker_id: str) -> int:
    """Returns a unique tcp port for each pytest-xdist worker to use"""
    if worker_id == "master":
        return 6110
    elif worker_id.startswith("gw"):  # are on the format "gw\d+"
        offset = int(worker_id[2:])
        return 6111 + offset
    else:
        msg = f"Unexpected {worker_id=}"
        raise ValueError(msg)


def exploration_server_process_fixture(
    tcp_port: int, server_binary_path: Path
) -> t.Iterator[None]:
    args = [server_binary_path.as_posix(), "--port", str(tcp_port)]
    env = {"ACC_MOCK_TEST_PATTERN": "1"}

    with sp.Popen(args, stdout=sp.PIPE, text=True, env=env) as server:
        while "waiting" not in server.stdout.readline().lower():
            if server.poll() is not None:
                pytest.fail("Server exited prematurely")

        yield
        server.terminate()


@pytest.fixture(scope="function")
def a121_exploration_server(
    worker_tcp_port: int, a121_exploration_server_path: Path
) -> t.Iterator[None]:
    yield from exploration_server_process_fixture(worker_tcp_port, a121_exploration_server_path)


@pytest.fixture(scope="function")
def a111_exploration_server(
    worker_tcp_port: int, a111_exploration_server_path: Path
) -> t.Iterator[None]:
    yield from exploration_server_process_fixture(worker_tcp_port, a111_exploration_server_path)
