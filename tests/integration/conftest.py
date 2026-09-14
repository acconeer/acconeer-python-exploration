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
    fuzzing_a121_worker_tcp_port: int, a121_exploration_server_path: Path
) -> t.Iterator[None]:
    # NOTE!
    # This server might be running at the same time as the servers managed by the
    # "a121_exploration_server" fixture

    args = [a121_exploration_server_path.as_posix(), "--port", str(fuzzing_a121_worker_tcp_port)]
    env = {"ACC_MOCK_TEST_PATTERN": "1"}

    # Don't capture stdout as it introduces overhead/risks blocking
    with sp.Popen(args, env=env) as server:
        # Assume startup takes 0.5 s.
        # Since this fixture is session-scoped, this sleep will only happen once.
        time.sleep(0.5)

        if server.poll() is not None:
            pytest.fail("Server exited prematurely")

        yield
        server.terminate()


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
