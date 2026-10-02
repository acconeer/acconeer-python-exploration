# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

from collections.abc import Iterator
from importlib.resources import as_file, files

import pytest

from acconeer.exptool import a121

from tests.processing.a121.data_files import recorded_data


@pytest.fixture
def client() -> Iterator[a121._ReplayingClient]:
    with (
        as_file(files(recorded_data) / "presence-low_power.h5") as path,
        a121.open_record(path) as record,
    ):
        client = a121._ReplayingClient(record, realtime_replay=False)
        client.setup_session(record.session(0).session_config)
        yield client


def test_get_next_before_start_raises(client: a121._ReplayingClient) -> None:
    with pytest.raises(a121.ClientError, match="not started"):
        client.get_next()


def test_stop_before_start_raises(client: a121._ReplayingClient) -> None:
    with pytest.raises(a121.ClientError, match="not started"):
        client.stop_session()


def test_get_next_after_stop_raises(client: a121._ReplayingClient) -> None:
    client.start_session()
    client.get_next()
    with pytest.warns(UserWarning, match="not exhausted"):
        client.stop_session()

    with pytest.raises(a121.ClientError, match="not started"):
        client.get_next()
