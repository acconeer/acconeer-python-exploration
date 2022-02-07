from __future__ import annotations

import os
import pathlib
from abc import ABC, abstractclassmethod, abstractmethod
from typing import Optional, Protocol, Sequence, Tuple, Union

from acconeer.exptool.structs.configbase import Config


_Description = str
_FileExtension = str
_Path = Union[str, pathlib.Path]
_AcceptedFileExtensions = Sequence[Tuple[_FileExtension, _Description]]


class Calibration(ABC):
    @abstractmethod
    def save(self, path: _Path):
        ...

    @abstractclassmethod
    def load(cls, path: _Path) -> Calibration:
        ...

    @abstractclassmethod
    def file_extensions(cls) -> _AcceptedFileExtensions:
        ...

    @classmethod
    def validate_path(cls, path: _Path) -> None:
        _, extension = os.path.splitext(path)
        extension = extension.strip(".")
        valid_extensions = [extension.strip(".") for ext, _ in cls.file_extensions()]

        extension_ok = extension in valid_extensions

        if not extension_ok:
            raise ValueError(
                (
                    f'Extension of file "{path}" ("{extension}") is not valid.'
                    + f"Should be one of {valid_extensions}."
                )
            )


class CalibrationMapper(Protocol):
    """
    This mapper is needed to allow for Configurations to contain a subset of the parameters
    in a Calibration. The configurable parameters (members of CalibrationConfiguration) are
    a subset (strict or non-strict) of the "actual" parameters in the Calibration.
    """

    @abstractclassmethod
    def get_updated_calibration_from_configuration(
        cls, configuration: Config, calibration: Optional[Calibration]
    ) -> Calibration:
        """
        Creates a new Calibration instance given a Config and (optionally) a Calibration.
        Fields in the Config should have precedence over the fields in the passed Calibration.

        This function is allowed to raise a ValueError if calibration=None is not supported.
        """
        ...

    @abstractclassmethod
    def update_config_from_calibration(
        cls, configuration: Config, calibration: Calibration
    ) -> None:
        """
        Updates the passed Config with the fields of the passed calibration.
        """
        ...
