def test_lib_version(ref_record, ref_lib_version):
    assert ref_record.lib_version == ref_lib_version


def test_server_info(ref_record, ref_server_info):
    assert ref_record.server_info == ref_server_info


def test_client_info(ref_record, ref_client_info):
    assert ref_record.client_info == ref_client_info


def test_timestamp(ref_record, ref_timestamp):
    assert ref_record.timestamp == ref_timestamp


def test_uuid(ref_record, ref_uuid):
    assert ref_record.uuid == ref_uuid


def test_data_layout(ref_record):
    assert [set(d.keys()) for d in ref_record._get_session_structure()] == [{2, 3}, {2}]

    assert ref_record._map_over_session_structure(lambda _: None) == [
        {2: None, 3: None},
        {2: None},
    ]
