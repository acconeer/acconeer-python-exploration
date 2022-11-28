# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from acconeer.exptool.a121._core.entities import PersistentRecord, Record
from acconeer.exptool.a121._core.peripherals.im_record import InMemoryRecord

from .record import H5Record
from .recorder import H5Recorder
from .utils import PathOrH5File, h5_file_factory


class RecordError(Exception):
    """Error in record handling"""


def open_record(path_or_file: PathOrH5File) -> PersistentRecord:
    """Open a record from file

    Since this function returns a :class:`PersistentRecord`, data is not immediately loaded into
    memory. Rather, data is lazily loaded from the underlying file on demand.

    Either a path or an opened file (:class:`h5py.File`) may be given. If a path is given, the file
    will be opened by this function, and must be closed again by the user. The recommended way to
    do this is by using the context manager of the returned persistent record, like:

    .. code-block:: python

        with a121.open_record("path/to/my/file.h5") as record:
            record.timestamp

    .. tip::

        Unless you're dealing with very large files, use :func:`load_record` instead.

    :returns: A :class:`PersistentRecord` wrapping the given file
    """

    file, _ = h5_file_factory(path_or_file, h5_file_mode="r")

    record_exc = RecordError(
        f"The file '{path_or_file}' is not an A121 record, try a111.recording.load instead"
    )
    try:
        generation = bytes(file["generation"][()]).decode()

        if generation != "a121":
            raise record_exc
    except Exception:
        raise record_exc

    return H5Record(file)


def load_record(path_or_file: PathOrH5File) -> Record:
    """Load a record from file

    Unlike :func:`open_record`, this functions loads the data into memory immediately. The file
    handle is not kept open.

    :returns: A :class:`Record` with the content of the given file
    """

    with open_record(path_or_file) as h5_record:
        return InMemoryRecord.from_record(h5_record)


def save_record(path_or_file: PathOrH5File, record: Record) -> None:
    """Alias for :func:`save_record_to_h5`"""

    return save_record_to_h5(path_or_file, record)


def save_record_to_h5(path_or_file: PathOrH5File, record: Record) -> None:
    """Save a record to a HDF5 file"""

    recorder = H5Recorder(path_or_file)

    recorder._start(
        client_info=record.client_info,
        extended_metadata=record.extended_metadata,
        server_info=record.server_info,
        session_config=record.session_config,
        calibrations=record.calibrations,
        calibrations_provided=record.calibrations_provided,
    )

    for extended_result in record.extended_results:
        recorder._sample(extended_result)

    recorder._stop()
