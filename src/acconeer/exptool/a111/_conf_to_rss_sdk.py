# Copyright (c) Acconeer AB, 2022
# All rights reserved


def config_to_rss_usage(self, config):
    # This table is used to translate names used by exploration tool, such as
    # 'tx_disable' to an RSS c-api equivalent. For example, 'acc_service_tx_disable_set' yields
    # 'acc_service_{service}_downsampling_factor_set' where {service} will be replaced by the
    # actual service, i.e 'envelope' or 'sparse'.
    # 'None' means that the exploration tool variable name has been
    # acknowledged but won't be used. For example, the 'range_end' does not exist
    # in RSS c-api anymore.
    # The 'update_rate' is not used unless we are in streaming mode so we only use it depending
    # on the value of 'repetition_mode'.
    # In the code below, the left hand side is named 'et_func' and the rhs is named 'rss_func'
    et_func_to_rss_func = {
        "downsampling_factor": "acc_service_{service}_downsampling_factor_set",
        "running_average_factor": "acc_service_{service}_running_average_factor_set",
        "noise_level_normalization": "acc_service_{service}_noise_level_normalization_set",
        "sweep_rate": "acc_service_{service}_configuration_sweep_rate_set",
        "sweeps_per_frame": "acc_service_{service}_configuration_sweeps_per_frame_set",
        "depth_lowpass_cutoff_ratio": "acc_service_{service}_depth_lowpass_cutoff_ratio_set",
        "bin_count": "acc_service_{service}_requested_bin_count_set",
        "power_save_mode": "acc_service_power_save_mode_set",
        "asynchronous_measurement": "acc_service_asynchronous_measurement_set",
        "hw_accelerated_average_samples": "acc_service_hw_accelerated_average_samples_set",
        "gain": "acc_service_receiver_gain_set",
        "mur": "acc_service_mur_set",
        "maximize_signal_attenuation": "acc_service_maximize_signal_attenuation_set",
        "sensor": "acc_service_sensor_set",
        "tx_disable": "acc_service_tx_disable_set",
        "profile": "acc_service_profile_set",
        "range_start": "acc_service_requested_start_set",
        "range_length": "acc_service_requested_length_set",
        "update_rate": None,  # Only applicable when running in streaming mode
        "repetition_mode": None,  # Will print when we know if it's HOST/SENSOR DRIVEN
        "range_interval": None,  # Not needed since we have range_start & range_length
        "range_end": None,  # --||--
        "mode": None,  # Not needed since we know what mode we are using
        "sampling_mode": "acc_service_{service}_sampling_mode_set",
    }

    # The exploration tool variables are not as the RSS c-api expects. Hence we need
    # to translate those values to something that is understood by c-code .
    # In the code, the left side is named as 'et_arg' and the right hand side is used
    # as "rss_arg"
    et_arg_to_rss_arg = {
        "True": "true",
        "False": "false",
        "MUR.MUR_6": "ACC_SERVICE_MUR_6",
        "MUR.MUR_9": "ACC_SERVICE_MUR_9",
        "PowerSaveMode.OFF": "ACC_POWER_SAVE_MODE_OFF",
        "PowerSaveMode.SLEEP": "ACC_POWER_SAVE_MODE_SLEEP",
        "PowerSaveMode.READY": "ACC_POWER_SAVE_MODE_READY",
        "PowerSaveMode.ACTIVE": "ACC_POWER_SAVE_MODE_ACTIVE",
        "PowerSaveMode.HIBERNATE": "ACC_POWER_SAVE_MODE_HIBERNATE",
        "Profile.PROFILE_1": "ACC_SERVICE_PROFILE_1",
        "Profile.PROFILE_2": "ACC_SERVICE_PROFILE_2",
        "Profile.PROFILE_3": "ACC_SERVICE_PROFILE_3",
        "Profile.PROFILE_4": "ACC_SERVICE_PROFILE_4",
        "Profile.PROFILE_5": "ACC_SERVICE_PROFILE_5",
        "RepetitionMode.HOST_DRIVEN": "HOST_DRIVEN",  # On demand
        "RepetitionMode.SENSOR_DRIVEN": "SENSOR_DRIVEN",  # Streaming
        "SamplingMode.A": "ACC_SERVICE_{service}_SAMPLING_MODE_A",
        "SamplingMode.B": "ACC_SERVICE_{service}_SAMPLING_MODE_B",
        "[1]": "1",
        "[2]": "2",
        "[3]": "3",
        "[4]": "4",
    }

    update_rate = 0  # Only used when we are running in streaming mode
    update_rate_and_rep_mode = 0  # This variable will be equal to 2 when we have
    # the update rate and we know that we are in streaming mode

    # Find out which service that is selected in the GUI
    service = str(getattr(config, "mode"))  # Yields "Mode.ENVELOPE"
    service = service.split(".")[1].lower()  # Yields "envelope"

    resultString = "// The following lines can be used in the update_configuration()"
    resultString += " method which is present in our example_service_" + service + ".c\n"

    # Find the argument in the example program used on update_config(). envelope_configuration,
    # sparse_configuration, power_bins_configuration or iq_configuration
    update_config_arg = service + "_configuration"

    for et_func, _ in self.get_sensor_config()._get_keys_and_params():
        et_arg = getattr(self.get_sensor_config(), et_func)
        rss_arg = et_arg_to_rss_arg.get(str(et_arg), str(et_arg))

        rss_func = et_func_to_rss_func.get(et_func)

        if rss_func is not None:
            rss_func = rss_func.format(service=service)

        if rss_arg is not None:
            rss_arg = rss_arg.format(service=service)

        if et_func == "sampling_mode" and service == "iq":
            resultString += "// No support for sampling_mode in iq service in RSS\n"
            continue

        # Special case - save update rate for later reference
        if et_func == "update_rate":
            update_rate = et_arg
            # Update rate needs repetition mode as well.
            update_rate_and_rep_mode += 1
        # Repetition mode is a also a special case since it renders in either
        # a call to acc_service_repetition_on_demand_set or ...streaming_set
        if et_func == "repetition_mode":
            if rss_arg == "HOST_DRIVEN":
                # We are host driven which means we don't need more info to print,
                # as opposed to sensor driven
                resultString += "acc_service_repetition_mode_on_demand_set"
                resultString += "(" + update_config_arg + ");\n"
            else:
                # Repetition mode needs update rate. Let's increase a counter
                update_rate_and_rep_mode += 1
        if update_rate_and_rep_mode == 2:
            # We are running in streaming mode (SENSOR_DRIVEN). And we have the update rate
            resultString += "acc_service_repetition_mode_streaming_set"
            resultString += "(" + update_config_arg + "," + str(update_rate) + ");\n"
            update_rate_and_rep_mode = 0
        # depth_lowpass_cutoff_ration demands a boolean which is a special case
        elif et_func == "depth_lowpass_cutoff_ratio":
            resultString += rss_func + "(" + update_config_arg + ", true, " + str(rss_arg) + ");\n"
        # Sweep rate can contain "None" instead of a number. Special case
        elif et_func == "sweep_rate":
            if rss_arg != str("None"):
                resultString += rss_func + "(" + update_config_arg + ", " + str(rss_arg) + ");\n"
        elif rss_func is not None:
            # General case
            resultString += rss_func + "(" + update_config_arg + ", " + rss_arg + ");\n"
    return resultString
