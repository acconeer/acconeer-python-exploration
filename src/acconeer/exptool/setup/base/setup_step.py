# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import abc
import subprocess
from pathlib import Path
from typing import List

from . import prompts


class SetupStep(abc.ABC):
    @abc.abstractmethod
    def report(self) -> None:
        """Prints a summary of what this setup step will do.

        This method will be called before `install()` to let the user
        abort.
        """
        pass

    @abc.abstractmethod
    def run(self) -> bool:
        """Performs the setup steps

        :returns: if the step ran successfully.
        """
        pass


class ShellCommandStep(SetupStep):
    """Runs a shell command as a step"""

    def __init__(self, command: List[str]) -> None:
        self.command = command

    def __str__(self) -> str:
        return "$ " + (" ".join(self.command))

    def report(self) -> None:
        print(self)

    def run(self) -> bool:
        print(f">>> {self!s}")
        completed_process = subprocess.run(self.command)
        return completed_process.returncode == 0


class RequireFileContentStep(ShellCommandStep):
    """Makes sure `required_content` is the exact content in `file_path`.

    If `file_path` does not exist, an attempt will be made to create it with `required_countent`.
    """

    def __init__(self, file_path: str, required_content: str, sudo: bool = False) -> None:
        super().__init__(
            (["sudo"] if sudo else [])
            + ["sh", "-c", f"echo -n '{required_content}' > {file_path}"]
        )
        self.file_path = Path(file_path)
        self.required_content = required_content

    def report(self) -> None:
        print(f"Will make sure that {self.file_path} contains this content:")
        print()
        print(f"    {self.required_content!r}")
        print()

    def run(self) -> bool:
        print(f">>> checking {self.file_path}")

        if self.file_path.exists():
            if self._report_on_content():
                return True
            else:
                if not prompts.yn_prompt(
                    f"WARNING: File {self.file_path} already exists with different content\n"
                    "Update existing file?"
                ):
                    return True

        creation_ok = super().run()
        return creation_ok and self._report_on_content()

    def _report_on_content(self) -> bool:
        if self.required_content == self.file_path.read_text():
            print(f"{self.file_path} looks good.")
            return True

        print(f"The contents of {self.file_path} does not match.")
        print()
        print("Actual:")
        for line in self.file_path.read_text().split("\n"):
            print(f"<   {line}")
        print("Expected:")
        for line in self.required_content.split("\n"):
            print(f">   {line}")
        print()

        return False
