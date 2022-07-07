import h5py

from acconeer.exptool import a121


def test_close_h5_record(tmp_file_path):
    file = h5py.File(tmp_file_path, "x")

    try:
        record = a121.open_record(file)
        assert file
        record.close()
        assert not file
    finally:
        file.close()


def test_open_record(ref_record_file):
    with a121.open_record(ref_record_file) as ref_record:
        assert isinstance(ref_record, a121.H5Record)


def test_load_record(ref_record_file):
    ref_record = a121.load_record(ref_record_file)
    assert isinstance(ref_record, a121.InMemoryRecord)
