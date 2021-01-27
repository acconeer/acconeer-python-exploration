import sys
from itertools import chain
from pathlib import Path

import pytest

import acconeer.exptool as et


HERE = Path(__file__).parent
path = (HERE / ".." / ".." / "utils").resolve()
sys.path.append(path.as_posix())

from convert_to_csv import record_to_csv  # noqa: E402


@pytest.mark.parametrize("test_file", chain(HERE.glob("**/*.h5"), HERE.glob("**/*.npz")))
def test_csv_conversion_is_exact(test_file):
    # The idea is to test the csv conversion corresponds exactly to the data file.
    # Aimed to catch rounding errors and flipped cols/rows.
    record = et.recording.load(test_file)
    if record.mode == et.Mode.SPARSE:
        pytest.skip("CSV-ifying of sparse data is not supported at this moment.")

    data = record.data.squeeze()
    assert data.ndim == 2

    csv_table = record_to_csv(record)
    csv_table_sac = record_to_csv(record, sweep_as_column=True)

    assert data.shape == csv_table.shape
    assert data.T.shape == csv_table_sac.shape

    for row in range(data.shape[0]):
        for col in range(data.shape[1]):
            assert data[row, col] == complex(csv_table[row, col])
            assert data[row, col] == complex(csv_table_sac[col, row])
