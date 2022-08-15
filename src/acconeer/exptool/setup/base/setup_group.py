# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from .setup_step import SetupStep


class SetupGroup(SetupStep):
    """Composite SetupStep"""

    def __init__(self, *steps: SetupStep) -> None:
        self.__steps: list[SetupStep] = list(steps)

    def add_steps(self, *steps: SetupStep) -> None:
        self.__steps.extend(steps)

    def report(self) -> None:
        for step in self.__steps:
            step.report()

    def run(self) -> bool:
        """Runs steps in a &&-like fashion."""
        for step in self.__steps:
            success = step.run()
            if not success:
                return False
        return True
