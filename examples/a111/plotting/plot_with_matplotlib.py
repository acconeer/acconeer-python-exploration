# Copyright (c) Acconeer AB, 2022
# All rights reserved

import matplotlib.pyplot as plt
import numpy as np

import acconeer.exptool as et


def main():
    args = et.a111.ExampleArgumentParser(num_sens=1).parse_args()
    et.utils.config_logging(args)

    client = et.a111.Client(**et.a111.get_client_args(args))

    config = et.a111.IQServiceConfig()
    config.sensor = args.sensors
    config.update_rate = 10

    session_info = client.setup_session(config)
    depths = et.a111.get_range_depths(config, session_info)

    amplitude_y_max = 1000

    fig, (amplitude_ax, phase_ax) = plt.subplots(2)
    fig.set_size_inches(8, 6)
    fig.canvas.set_window_title("Acconeer matplotlib example")

    for ax in [amplitude_ax, phase_ax]:
        ax.set_xlabel("Depth (m)")
        ax.set_xlim(config.range_interval)
        ax.grid(True)

    amplitude_ax.set_ylabel("Amplitude")
    amplitude_ax.set_ylim(0, 1.1 * amplitude_y_max)
    phase_ax.set_ylabel("Phase")
    et.utils.mpl_setup_yaxis_for_phase(phase_ax)

    amplitude_line = amplitude_ax.plot(depths, np.zeros_like(depths))[0]
    phase_line = phase_ax.plot(depths, np.zeros_like(depths))[0]

    fig.tight_layout()
    plt.ion()
    plt.show()

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    client.start_session()

    while not interrupt_handler.got_signal:
        info, data = client.get_next()

        amplitude = np.abs(data)
        phase = np.angle(data)

        max_amplitude = np.max(amplitude)
        if max_amplitude > amplitude_y_max:
            amplitude_y_max = max_amplitude
            amplitude_ax.set_ylim(0, 1.1 * max_amplitude)

        amplitude_line.set_ydata(amplitude)
        phase_line.set_ydata(phase)

        if not plt.fignum_exists(1):  # Simple way to check if plot is closed
            break

        fig.canvas.flush_events()

    print("Disconnecting...")
    plt.close()
    client.disconnect()


if __name__ == "__main__":
    main()
