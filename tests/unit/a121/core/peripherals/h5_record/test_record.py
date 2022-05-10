"""
These test doesn't look like much, but the tested member
(ref_lib_version, ref_server_info, etc.) have taken a
round-trip through:

1. Serialization
2. Saved to disk
3. Loaded through H5Record
4. Deserialization
5. ... and finally compared.
"""

import numpy as np


def test_lib_version(ref_record, ref_lib_version):
    assert ref_record.lib_version == ref_lib_version


def test_server_info(ref_record, ref_server_info):
    assert ref_record.server_info == ref_server_info


def test_client_info(ref_record, ref_client_info):
    assert ref_record.client_info == ref_client_info


def test_session_config(ref_record, ref_session_config):
    assert ref_record.session_config == ref_session_config


def test_extended_metadata(ref_record, ref_metadata):
    for group in ref_record.extended_metadata:
        for sensor_id, metadata in group.items():
            assert metadata == ref_metadata


def test_timestamp(ref_record, ref_timestamp):
    assert ref_record.timestamp == ref_timestamp


def test_uuid(ref_record, ref_uuid):
    assert ref_record.uuid == ref_uuid


def test_data_layout(ref_record, ref_structure):
    assert [set(d.keys()) for d in ref_record._get_entries()] == ref_structure


def test_extended_results(ref_record, ref_frame_raw, ref_frame):
    for measurement in ref_record.extended_results:
        for group in measurement:
            for sensor_id, result in group.items():
                np.testing.assert_array_equal(result._frame, ref_frame_raw)
                np.testing.assert_array_equal(result.frame, ref_frame)


def test_num_frames(ref_record, ref_num_frames):
    assert ref_record.num_frames == ref_num_frames


def test_stacked_results_num_frames(ref_record, ref_num_frames, ref_structure):
    for group_id, group in enumerate(ref_structure):
        for sensor_id in group:
            assert len(ref_record.extended_stacked_results[group_id][sensor_id]) == ref_num_frames


def test_stacked_results_data(ref_record, ref_frame, ref_structure):
    for group_id, group in enumerate(ref_structure):
        for sensor_id in group:
            for frame in ref_record.extended_stacked_results[group_id][sensor_id].frame:
                np.testing.assert_array_equal(frame, ref_frame)
