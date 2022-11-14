# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import abc
from typing import Any, Iterator

import numpy as np
import numpy.typing as npt

from acconeer.exptool.a121._core import utils
from acconeer.exptool.a121._core.entities.configs import SessionConfig

from .client_info import ClientInfo
from .metadata import Metadata
from .result import Result
from .sensor_calibration import SensorCalibration
from .server_info import ServerInfo
from .stacked_results import StackedResults


class RecordException(Exception):
    pass


class Record(abc.ABC):
    """Record representing all data needed to recreate a session"""

    @property
    @abc.abstractmethod
    def client_info(self) -> ClientInfo:
        """Client info"""

    @property
    @abc.abstractmethod
    def extended_metadata(self) -> list[dict[int, Metadata]]:
        """Extended metadata"""

    @property
    def metadata(self) -> Metadata:
        """Retrieves the sole metadata entry in the record

        :raises: ValueError if there are multiple entries in the :attr:`extended_metadata`
        """

        return utils.unextend(self.extended_metadata)

    @property
    @abc.abstractmethod
    def extended_results(self) -> Iterator[list[dict[int, Result]]]:
        """The sequence of extended results

        Retrieves an iterator over all extended results in the record, which may be useful to
        replay a session.

        .. tip::

            If your record only has one entry in the session, and you want to retrieve the results
            for that one entry, you can use :attr:`results`.

            If you desire to get, for example, all frames in the sequence of results stacked in one
            array, use
            :attr:`extended_stacked_results`. Similar to :attr:`results`, there is also
            :attr:`stacked_results` which retrieves the one and only entry.
        """

    @property
    def results(self) -> Iterator[Result]:
        """Retrieves the sole sequence of results in the record

        :raises: ValueError if there are multiple entries in the :attr:`extended_results`
        """

        for extended_result in self.extended_results:
            yield utils.unextend(extended_result)

    @property
    @abc.abstractmethod
    def extended_stacked_results(self) -> list[dict[int, StackedResults]]:
        """The extended stacked results"""

    @property
    def stacked_results(self) -> StackedResults:
        """Retrieves the sole stacked results in the record

        :raises: ValueError if there are multiple entries in the :attr:`extended_stacked_results`
        """

        return utils.unextend(self.extended_stacked_results)

    @property
    def frames(self) -> npt.NDArray[np.complex_]:
        """Retrieves the sole stack of frames in the record

        Alias for ``Record.stacked_results.frame``.

        :raises: ValueError if there are multiple entries in the :attr:`extended_stacked_results`
        """

        return self.stacked_results.frame

    @property
    @abc.abstractmethod
    def lib_version(self) -> str:
        """The version of the ``acconeer.exptool`` library which created the record"""

    @property
    @abc.abstractmethod
    def num_frames(self) -> int:
        """The number of frames in the record"""

    @property
    @abc.abstractmethod
    def server_info(self) -> ServerInfo:
        """Server info"""

    @property
    @abc.abstractmethod
    def session_config(self) -> SessionConfig:
        """Session config"""

    @property
    @abc.abstractmethod
    def sensor_id(self) -> int:
        """The sole sensor ID

        :raises: ValueError if there are multiple entries in the :attr:`session_config`
        """

    @property
    @abc.abstractmethod
    def timestamp(self) -> str:
        """Creation timestamp"""

    @property
    @abc.abstractmethod
    def uuid(self) -> str:
        """UUID"""

    @property
    @abc.abstractmethod
    def calibrations(self) -> dict[int, SensorCalibration]:
        """The calibrations in the record"""

    @property
    @abc.abstractmethod
    def calibrations_provided(self) -> dict[int, bool]:
        """The calibrations provided in the record"""


class PersistentRecord(Record):
    """Record that wraps a file on disk

    Data is lazily loaded from the underlying file on demand.
    """

    @abc.abstractmethod
    def close(self) -> None:
        """Close the underlying file"""

    def __enter__(self) -> Record:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
