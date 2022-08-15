# Copyright (c) Acconeer AB, 2022
# All rights reserved

import acconeer.exptool as et
from acconeer.exptool.a111.algo import ModuleInfo


def main(module_info: ModuleInfo):
    arg_parse_kwargs = {} if module_info.multi_sensor else dict(num_sens=1)
    args = et.a111.ExampleArgumentParser(**arg_parse_kwargs).parse_args()
    et.utils.config_logging(args)

    client = et.a111.Client(**et.a111.get_client_args(args))

    client.squeeze = not module_info.multi_sensor

    sensor_config = module_info.sensor_config_class()
    processing_config = module_info.processing_config_class()
    sensor_config.sensor = args.sensors

    session_info = client.setup_session(sensor_config)

    pg_updater = module_info.pg_updater(sensor_config, processing_config, session_info)
    pg_process = et.PGProcess(pg_updater)
    pg_process.start()

    client.start_session()

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    processor = module_info.processor(sensor_config, processing_config, session_info)

    while not interrupt_handler.got_signal:
        info, sweep = client.get_next()
        processed_data = processor.process(sweep, info)

        if processed_data is not None:
            if hasattr(processor, "update_calibration"):
                new_calibration = processed_data.get("new_calibration")
                if new_calibration is not None:
                    processor.update_calibration(new_calibration)

            try:
                pg_process.put_data(processed_data)
            except et.PGProccessDiedException:
                break

    print("Disconnecting...")
    pg_process.close()
    client.disconnect()
