import numpy as np
import matplotlib.pyplot as plt

from acconeer_utils.clients.reg.client import RegClient
from acconeer_utils.clients.json.client import JSONClient
from acconeer_utils.clients import configs
from acconeer_utils import example_utils


def main():
    args = example_utils.ExampleArgumentParser(num_sens=1).parse_args()
    example_utils.config_logging(args)

    if args.socket_addr:
        client = JSONClient(args.socket_addr)
    else:
        port = args.serial_port or example_utils.autodetect_serial_port()
        client = RegClient(port)

    config = configs.IQServiceConfig()
    config.sensor = args.sensors
    config.range_interval = [0.2, 0.6]
    config.sweep_rate = 10
    config.gain = 0.6

    info = client.setup_session(config)
    num_points = info["data_length"]

    amplitude_y_max = 0.3

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
    example_utils.mpl_setup_yaxis_for_phase(phase_ax)

    xs = np.linspace(*config.range_interval, num_points)
    amplitude_line = amplitude_ax.plot(xs, np.zeros_like(xs))[0]
    phase_line = phase_ax.plot(xs, np.zeros_like(xs))[0]

    fig.tight_layout()
    plt.ion()
    plt.show()

    interrupt_handler = example_utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    client.start_streaming()

    while not interrupt_handler.got_signal:
        info, sweep = client.get_next()

        amplitude = np.abs(sweep)
        phase = np.angle(sweep)

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
