import sys
from pathlib import Path

import pytest

import acconeer.exptool as et


HERE = Path(__file__).parent
path = (HERE / ".." / ".." / "utils").resolve()
sys.path.append(path.as_posix())

from convert_to_csv import A111RecordTableConverter  # noqa: E402


@pytest.mark.parametrize("test_file", (HERE / ".." / "processing").glob("**/input.h5"))
def test_csv_conversion_is_exact(test_file):
    # The idea is to test the csv conversion corresponds exactly to the data file.
    # Aimed to catch rounding errors and flipped cols/rows.
    record = et.a111.recording.load(test_file)
    if record.mode == et.a111.Mode.SPARSE:
        pytest.skip("CSV-ifying of sparse data is not supported at this moment.")

    data = record.data.squeeze()
    assert data.ndim == 2

    csv_table = A111RecordTableConverter(record).convert(0)

    assert data.shape == csv_table.shape

    for row in range(data.shape[0]):
        for col in range(data.shape[1]):
            assert data[row, col] == complex(csv_table[row, col])
