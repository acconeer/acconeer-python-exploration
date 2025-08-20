# Copyright (c) Acconeer AB, 2022-2025
# All rights reserved

import sys
from pathlib import Path

import pytest

import acconeer.exptool as et


HERE = Path(__file__).parent
path = (HERE / ".." / ".." / "user_tools").resolve()
sys.path.append(path.as_posix())

from convert_h5 import A111RecordTableConverter  # noqa: E402


@pytest.mark.parametrize("test_file", (HERE / ".." / "processing" / "a111").glob("**/input.h5"))
def test_csv_conversion_is_exact(test_file):
    # The idea is to test the csv conversion corresponds exactly to the data file.
    # Aimed to catch rounding errors and flipped cols/rows.
    record = et.a111.recording.load(test_file)
    if record.mode == et.a111.Mode.SPARSE:
        pytest.skip("CSV-ifying of sparse data is not supported at this moment.")

    data = record.data.squeeze()
    assert data.ndim == 2
    # A111 provide 1D of list, following A121 format as sparse iq lists of multiple sessions and sensors
    csv_table = A111RecordTableConverter(record).convert(0)[0]

    assert data.shape == csv_table.shape

    for row in range(data.shape[0]):
        for col in range(data.shape[1]):
            assert data[row, col] == complex(csv_table[row, col])
