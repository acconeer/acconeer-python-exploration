# Copyright (c) Acconeer AB, 2022
# All rights reserved

from .setup_step import SetupStep


class WithDescription(SetupStep):
    """Decorates a SetupStep by `report`ing a description
    before reporting the step
    """

    def __init__(self, description: str, step: SetupStep) -> None:
        self.description = description
        self.step = step

    def report(self) -> None:
        print(self.description)
        self.step.report()
        print()

    def run(self) -> bool:
        return self.step.run()
