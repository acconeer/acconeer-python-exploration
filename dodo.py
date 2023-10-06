# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved
"""
This is the configuration file for "doit" (https://pydoit.org/)

$ doit                  # runs all tasks
$ doit -n 2             # runs all tasks, while utilizing 2 processes
$ doit list             # lists all tasks
$ doit list --all       # lists all tasks, including subtasks
$ doit <task1> <task2>  # runs task1 & task2
"""

import doit


PYTHON_VERSIONS = ("3.8", "3.9", "3.10", "3.11", "3.12")
GENERATIONS = ("a121", "a111")

CLI_ARGS = {"port_strategy": doit.get_var("port_strategy", "unique")}


def task_integration_test():
    """Integration test against the mock server on different Python versions"""
    for py_ver in PYTHON_VERSIONS:
        for gen in GENERATIONS:
            if CLI_ARGS["port_strategy"] == "unique":
                port = 6000 + (int(py_ver[2:]) * int(gen[1:]))
                yield {
                    "name": f"{py_ver}-{gen}",
                    "actions": [f"tests/run-{gen}-mock-integration-tests.sh {py_ver} {port}"],
                }
            else:
                yield {
                    "name": f"{py_ver}-{gen}",
                    "actions": [f"tests/run-{gen}-mock-integration-tests.sh {py_ver}"],
                }


def task_test():
    """Unit & integration tests on different Python versions"""
    for py_ver in PYTHON_VERSIONS:
        yield {
            "name": py_ver,
            "actions": [
                f"hatch run test.py{py_ver}:unit",
                f"hatch run test.py{py_ver}:processing",
                f"hatch run test.py{py_ver}:doctest",
            ],
        }
