# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

# type: ignore

import enum
import json

import packaging.version
import pytest

from acconeer.exptool.a121._core import utils


def test_convert_validate_int_ok_value():
    _ = utils.convert_validate_int(3)
    _ = utils.convert_validate_int(3.0)


def test_convert_validate_int_type_errors():
    with pytest.raises(TypeError):
        _ = utils.convert_validate_int("3")

    with pytest.raises(TypeError):
        _ = utils.convert_validate_int(3.5)


def test_convert_validate_int_boundaries():
    with pytest.raises(ValueError):
        _ = utils.convert_validate_int(0, min_value=1)

    with pytest.raises(ValueError):
        _ = utils.convert_validate_int(1, max_value=0)


def test_validate_float_ok_value():
    _ = utils.validate_float(3.1)
    _ = utils.validate_float(3.1, max_value=3.1)
    _ = utils.validate_float(3.1, min_value=3.1)
    _ = utils.validate_float(3.1, min_value=3.0, max_value=3.2)


def test_validate_float_type_errors():
    with pytest.raises(TypeError):
        _ = utils.validate_float("3.1")


def test_validate_float_boundaries():
    with pytest.raises(ValueError):
        _ = utils.validate_float(0.0, min_value=1.0)

    with pytest.raises(ValueError):
        _ = utils.validate_float(1.0, max_value=0.0)

    with pytest.raises(ValueError):
        _ = utils.validate_float(0.0, max_value=0.0, inclusive=False)

    with pytest.raises(ValueError):
        _ = utils.validate_float(0.1, min_value=0.0, max_value=0.1, inclusive=False)


def test_unextend():
    argument = [{1: "test"}]
    assert utils.unextend(argument) == "test"


def test_unextend_bad_argument():
    argument = ["test"]
    with pytest.raises(ValueError):
        utils.unextend(argument)


def test_create_extended_structure():
    structure = [{2: "foo", 1: "bar"}, {1: "baz"}]
    items = utils.iterate_extended_structure(structure)
    recreated_structure = utils.create_extended_structure(items)

    assert [list(d.items()) for d in recreated_structure] == [list(d.items()) for d in structure]

    # Catch that we must start with group index 0
    with pytest.raises(ValueError):
        utils.create_extended_structure([(1, 0, "foo")])

    # Catch that we can't skip a group index
    with pytest.raises(ValueError):
        utils.create_extended_structure([(0, 0, "foo"), (2, 0, "bar")])

    # Catch duplicate sensor id in a group
    with pytest.raises(ValueError):
        utils.create_extended_structure([(0, 0, "foo"), (0, 0, "bar")])


def test_entity_json_encoder():
    SomeEnum = enum.Enum("SomeEnum", ["FOO", "BAR"])
    assert SomeEnum.FOO.value == 1

    dump_dict = {
        "some_enum_value": SomeEnum.BAR,
        "some_other_value": 123,
    }
    expected = {
        "some_enum_value": "BAR",
        "some_other_value": 123,
    }
    actual = json.loads(json.dumps(dump_dict, cls=utils.EntityJSONEncoder))

    assert actual == expected
    for k, expected_v in expected.items():
        assert type(actual[k]) is type(expected_v)


@pytest.mark.parametrize(
    ("raw", "version"),
    [
        ("a121-v1.2.3", "1.2.3"),
        ("a121-v1.2.3-rc4", "1.2.3rc4"),
        ("a121-v1.2.3-123-g0e03503be1", "1.2.4.dev123+g0e03503be1"),
        ("a121-v1.2.3-rc4-123-g0e03503be1", "1.2.3rc5.dev123+g0e03503be1"),
    ],
)
def test_parse_rss_version(raw, version):
    assert utils.parse_rss_version(raw) == packaging.version.Version(version)


def test_rss_version_order():
    correctly_ordered_versions = [
        "a121-v1.2.3",
        "a121-v1.2.3-1-g123",
        "a121-v1.2.3-2-g123",
        "a121-v1.2.4-rc1",
        "a121-v1.2.4-rc1-1-g123",
        "a121-v1.2.4-rc1-2-g123",
        "a121-v1.2.4-rc2",
        "a121-v1.2.4-rc2-1-g123",
        "a121-v1.2.4",
    ]
    correctly_ordered_versions = [utils.parse_rss_version(s) for s in correctly_ordered_versions]
    assert correctly_ordered_versions == sorted(correctly_ordered_versions)


@pytest.mark.parametrize(
    ("structures", "expected"),
    [(([{1: "a"}], [{1: "b"}], [{1: "c"}]), [{1: ("a", "b", "c")}])],  # structures  # expected
)
def test_zip3_extended_structures(structures, expected):
    assert utils.zip3_extended_structures(*structures) == expected


@pytest.mark.parametrize(
    "structures",
    [
        ([{1: "a"}], [{1: "b"}], [{2: "c"}]),
        ([{1: "a", 2: "a"}], [{1: "b", 2: "b"}], [{2: "c"}]),
    ],
)
def test_zip3_extended_structures_with_bad_arguments(structures):
    with pytest.raises(ValueError):
        utils.zip3_extended_structures(*structures)


def test_transpose_extended_structures():
    structures = [
        [{1: "a"}, {2: "x"}],
        [{1: "b"}, {2: "y"}],
        [{1: "c"}, {2: "z"}],
    ]
    expected = [
        {1: ["a", "b", "c"]},
        {2: ["x", "y", "z"]},
    ]
    assert utils.transpose_extended_structures(structures) == expected


def test_transpose_extended_structures_empty():
    with pytest.raises(ValueError):
        _ = utils.transpose_extended_structures([])


def test_transpose_extended_structures_all_structures_needs_to_have_same_structure():
    structures = [
        [{1: "a"}],
        [],
    ]
    with pytest.raises(ValueError):
        _ = utils.transpose_extended_structures(structures)


def test_extended_structure_shape():
    assert utils.extended_structure_shape([{1: "a", 2: "b"}, {3: "c"}]) == [{1, 2}, {3}]
