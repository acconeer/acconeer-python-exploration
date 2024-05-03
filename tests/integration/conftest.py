# Copyright (c) Acconeer AB, 2024
# All rights reserved

import subprocess as sp
import typing as t
from pathlib import Path

import pytest


def server_path(generation: str) -> Path:
    et_root = Path(__file__).parents[2]
    bin_name = f"acc_exploration_server_{generation}"
    return et_root / f"stash/out/customer/{generation}/internal_sanitizer_x86_64/out/" / bin_name


@pytest.fixture(scope="session")
def worker_tcp_port(worker_id: str) -> int:
    """Returns a unique tcp port for each pytest-xdist worker to use"""
    if worker_id == "master":
        return 6110
    elif worker_id.startswith("gw"):  # are on the format "gw\d+"
        offset = int(worker_id[2:])
        return 6111 + offset
    else:
        raise ValueError(f"Unexpected {worker_id=}")


@pytest.fixture(scope="function")
def a121_exploration_server(worker_tcp_port: int) -> t.Iterator[None]:
    assert server_path("a121").exists(), "Could not find a121 mock exploration server"

    args = [server_path("a121").as_posix(), "--port", str(worker_tcp_port)]
    env = {"ACC_MOCK_TEST_PATTERN": "1"}

    with sp.Popen(args, stdout=sp.PIPE, text=True, env=env) as server:
        while "waiting" not in server.stdout.readline().lower():
            pass  # The server prints "Waiting for new connections..."

        yield
        server.terminate()


@pytest.fixture(scope="function")
def a111_exploration_server(worker_tcp_port: int) -> t.Iterator[None]:
    assert server_path("a111").exists(), "Could not find a111 mock exploration server"

    args = [server_path("a111").as_posix(), "--port", str(worker_tcp_port)]
    env = {"ACC_MOCK_TEST_PATTERN": "1"}

    with sp.Popen(args, stdout=sp.PIPE, text=True, env=env) as server:
        while "waiting" not in server.stdout.readline().lower():
            pass  # The server prints "Waiting for new connections..."

        yield
        server.terminate()
