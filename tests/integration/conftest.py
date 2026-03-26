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

    server_logs = []
    with sp.Popen(args, stdout=sp.PIPE, stderr=sp.STDOUT, text=True, env=env) as server_process:
        server_stdout = server_process.stdout
        assert server_stdout is not None

        while True:
            if server_process.poll() is not None:
                pytest.fail("Server exited prematurely")

            server_log = server_stdout.readline()
            server_logs.append(server_log)

            if "waiting" in server_log.lower():
                break

        yield  # give control to test function

        server_process.terminate()  # stop server and close write-end of pipe

        while True:
            server_log = server_stdout.readline()
            server_logs.append(server_log)

            if server_log == "":  # "" is read when no more data is left to read
                break

        print(*server_logs, sep="")


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
