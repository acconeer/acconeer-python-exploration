import inspect

import pytest

import acconeer.exptool.structs.configbase as cb
from acconeer.exptool.a111 import _configs
from acconeer.exptool.a111._clients.reg import regmap
from acconeer.exptool.a111._modes import Mode


BO = regmap.BYTEORDER


def test_full_names_unique():
    unique_names = set([r.full_name for r in regmap.REGISTERS])
    assert len(regmap.REGISTERS) == len(unique_names)


def test_get_reg_status():
    reg = regmap.get_reg("status")
    assert reg.full_name == "status"
    assert reg == regmap.STATUS_REG
    assert reg.bitset_flags == regmap.STATUS_FLAGS
    assert reg.bitset_masks == regmap.STATUS_MASKS
    assert regmap.get_reg(reg) == reg
    assert regmap.get_reg(reg.addr) == reg


def test_get_reg():
    with pytest.raises(ValueError):
        regmap.get_reg("does-not-exist")

    assert regmap.get_reg("iq_stitch_count").full_name == "iq_stitch_count"
    assert regmap.get_reg("iq_stitch_count", "iq").full_name == "iq_stitch_count"
    assert regmap.get_reg("stitch_count", "iq").full_name == "iq_stitch_count"

    with pytest.raises(ValueError):
        regmap.get_reg("iq_stitch_count", "sparse")

    with pytest.raises(ValueError):
        regmap.get_reg("stitch_count")  # ambiguous

    reg = regmap.get_reg("sp_start")

    with pytest.raises(ValueError):
        regmap.get_reg(reg.addr)  # ambiguous

    assert regmap.get_reg(reg.addr, reg.modes[0]) == reg


def test_config_to_reg_map_completeness():
    all_param_keys = set()

    for mode, config_class in _configs.MODE_TO_CONFIG_CLASS_MAP.items():
        params = {k: v for k, v in inspect.getmembers(config_class) if isinstance(v, cb.Parameter)}
        all_param_keys.update(params.keys())

        expected_config_key_to_reg_map = {}

        for param_name, param in params.items():
            if param.is_dummy:
                continue

            reg_name = regmap.CONFIG_TO_STRIPPED_REG_NAME_MAP[param_name]

            if reg_name is None:
                continue

            reg = regmap.get_reg(reg_name, mode)

            assert reg.category in [regmap.Category.CONFIG, regmap.Category.GENERAL]

            expected_config_key_to_reg_map[param_name] = reg

        assert regmap.get_config_key_to_reg_map(mode) == expected_config_key_to_reg_map

    unknown_keys_in_map = set(regmap.CONFIG_TO_STRIPPED_REG_NAME_MAP.keys()) - all_param_keys
    assert not unknown_keys_in_map


def test_encode_bitset():
    reg = regmap.STATUS_REG
    assert reg.data_type == regmap.DataType.BITSET
    created = regmap.STATUS_FLAGS.CREATED
    activated = regmap.STATUS_FLAGS.ACTIVATED

    truth = int(activated).to_bytes(4, BO)
    assert reg.encode(activated) == truth
    assert reg.encode(int(activated)) == truth
    assert reg.encode("activated") == truth
    assert reg.encode("ACTIVATED") == truth
    assert reg.encode(["activated"]) == truth

    truth = int(0).to_bytes(4, BO)
    assert reg.encode([]) == truth
    assert reg.encode(0) == truth

    truth = int(created | activated).to_bytes(4, BO)
    assert reg.encode(created | activated) == truth
    assert reg.encode(["created", "activated"]) == truth


def test_decode_bitset():
    reg = regmap.STATUS_REG
    created = regmap.STATUS_FLAGS.CREATED
    activated = regmap.STATUS_FLAGS.ACTIVATED

    assert reg.decode(reg.encode(created)) == created
    assert reg.decode(reg.encode(created | activated)) == created | activated


def test_encode_enum():
    reg = regmap.get_reg("mode_selection")
    assert reg.data_type == regmap.DataType.ENUM
    envelope = reg.enum.ENVELOPE

    truth = int(envelope).to_bytes(4, BO)
    assert reg.encode(envelope) == truth
    assert reg.encode(int(envelope)) == truth
    assert reg.encode("envelope") == truth
    assert reg.encode("ENVELOPE") == truth

    # Implicit remapping
    assert reg.encode(Mode.ENVELOPE) == truth

    # Explicit remapping
    reg = regmap.get_reg("repetition_mode")
    truth = int(reg.enum.STREAMING).to_bytes(4, BO)
    assert reg.encode(_configs.BaseServiceConfig.RepetitionMode.SENSOR_DRIVEN) == truth


def test_decode_enum():
    reg = regmap.get_reg("mode_selection")
    envelope = reg.enum.ENVELOPE

    assert reg.decode(reg.encode(envelope)) == envelope


def test_encode_bool():
    reg = regmap.get_reg("tx_disable")
    assert reg.data_type == regmap.DataType.BOOL

    assert reg.encode(False) == int(0).to_bytes(4, BO)
    assert reg.encode(True) == int(1).to_bytes(4, BO)
    assert reg.encode(0) == int(0).to_bytes(4, BO)
    assert reg.encode(1) == int(1).to_bytes(4, BO)
    assert reg.encode(123) == int(1).to_bytes(4, BO)


def test_decode_bool():
    reg = regmap.get_reg("tx_disable")

    assert reg.decode(reg.encode(True)) is True


def test_encode_int():
    pass  # tested in float


def test_decode_int():
    pass


def test_encode_uint():
    reg = regmap.get_reg("downsampling_factor")
    assert reg.data_type == regmap.DataType.UINT32

    assert reg.encode(0) == int(0).to_bytes(4, BO, signed=True)
    assert reg.encode(1234) == int(1234).to_bytes(4, BO, signed=True)

    with pytest.raises(ValueError):
        reg.encode(-123)


def test_decode_uint():
    reg = regmap.get_reg("downsampling_factor")

    assert reg.decode(reg.encode(1234)) == 1234


def test_encode_float():
    reg = regmap.get_reg("range_start")
    assert reg.full_name == "range_start"
    assert reg.float_scale == pytest.approx(1000)
    assert reg.data_type == regmap.DataType.INT32

    assert reg.encode(0) == int(0).to_bytes(4, BO, signed=True)
    assert reg.encode(0.123) == int(123).to_bytes(4, BO, signed=True)
    assert reg.encode(-0.123) == int(-123).to_bytes(4, BO, signed=True)


def test_decode_float():
    reg = regmap.get_reg("range_start")

    assert reg.decode(reg.encode(0.123)) == pytest.approx(0.123)
