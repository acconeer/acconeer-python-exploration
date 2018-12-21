from acconeer_utils.clients.reg import protocol


def get_regs_for_mode(mode):
    mode = protocol.get_mode(mode)
    for reg in protocol.REGS:
        if reg.mode in [protocol.NO_MODE, mode]:
            yield reg


def get_session_info_regs(mode):
    return [reg for reg in get_regs_for_mode(mode) if reg.is_session_info]


def get_reg_vals_for_config(config):
    reg_vals = []
    for reg in get_regs_for_mode(config.mode):
        config_attr = reg.config_attr
        if config_attr is None:
            continue

        config_val = getattr(config, config_attr, None)

        if config_val is not None:
            enc_val = protocol.encode_reg_val(reg, config_val)
            rv = protocol.UnpackedRegVal(reg.addr, enc_val)
            reg_vals.append(rv)
    return reg_vals
