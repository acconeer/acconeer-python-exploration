from __future__ import annotations

from acconeer.exptool.a121._core.entities import PersistentRecord, Record

from .record import H5Record
from .recorder import H5Recorder
from .utils import PathOrH5File, h5_file_factory


def open_record(path_or_file: PathOrH5File) -> PersistentRecord:
    file, _ = h5_file_factory(path_or_file, h5_file_mode="r")
    return H5Record(file)


def load_record(path_or_file: PathOrH5File) -> Record:
    raise NotImplementedError


def save_record(path_or_file: PathOrH5File, record: Record) -> None:
    return save_record_to_h5(path_or_file, record)


def save_record_to_h5(path_or_file: PathOrH5File, record: Record) -> None:
    recorder = H5Recorder(path_or_file)

    recorder.start(
        client_info=record.client_info,
        extended_metadata=record.extended_metadata,
        server_info=record.server_info,
        session_config=record.session_config,
    )

    for extended_result in record.extended_results:
        recorder.sample(extended_result)

    recorder.stop()
