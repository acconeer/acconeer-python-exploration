# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved

from __future__ import annotations

from acconeer.exptool._core.recording.h5_record.utils import PathOrH5File, h5_file_factory

from .h5_record import H5Record
from .h5_recorder import H5Recorder


class RecordError(Exception):
    """Error in record handling"""


def open_record(path_or_file: PathOrH5File) -> H5Record:
    """Open a record from file

    Since this function returns a :class:`H5Record`, data is not immediately loaded into
    memory. Rather, data is lazily loaded from the underlying file on demand.

    Either a path or an opened file (:class:`h5py.File`) may be given. If a path is given, the file
    will be opened by this function, and must be closed again by the user. The recommended way to
    do this is by using the context manager of the returned persistent record, like:

    .. code-block:: python

        with a2.open_record("path/to/my/file.h5") as record:
            record.timestamp

    :returns: A :class:`H5Record` wrapping the given file
    """

    file, _ = h5_file_factory(path_or_file, h5_file_mode="r")

    record_exc = RecordError(f"The file '{path_or_file}' is not an A2 record")
    try:
        generation = bytes(file["generation"][()]).decode()

        if generation not in ["a2", "a211"]:
            raise record_exc
    except Exception:
        raise record_exc

    return H5Record(file)


def save_record(path_or_file: PathOrH5File, record: H5Record) -> None:
    """Save a record to a HDF5 file"""

    with H5Recorder(path_or_file) as r:
        r._start(client_info=record.client_info, server_info=record.server_info)

        for session in (record.session(i) for i in range(record.num_sessions)):
            r._start_session(config=session.session_config, metadata=session.metadata)

            for group_result in session.group_results:
                r._sample(group_result)

            r._stop_session()
