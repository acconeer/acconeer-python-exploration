import numpy as np
import matplotlib.pyplot as plt

from acconeer_utils.streaming_client import StreamingClient
from acconeer_utils.config_builder import ConfigBuilder
from acconeer_utils.example_argparse import ExampleArgumentParser


class IQMPLExample:
    def run(self):
        parser = ExampleArgumentParser()
        args = parser.parse_args()

        range_start = 0.20
        range_end = 0.50

        self.plot_x_min = int(100 * range_start + 0.5)
        self.plot_x_max = int(100 * range_end + 0.5)
        self.sweep_index = 0
        self.amplitude_y_max = 1000

        self.fig, (self.ampl_ax, self.phase_ax) = plt.subplots(2)
        self.fig.set_size_inches(8, 6)
        self.fig.canvas.set_window_title("Acconeer IQ data example")

        for ax in [self.ampl_ax, self.phase_ax]:
            ax.set_xlabel("Depth (cm)")
            ax.set_xlim(self.plot_x_min, self.plot_x_max)
            ax.grid(True)

        self.ampl_ax.set_ylabel("Amplitude")
        self.ampl_ax.set_ylim(0, 1.1 * self.amplitude_y_max)

        self.phase_ax.set_ylabel("Phase")
        self.phase_ax.set_ylim(-np.pi, np.pi)
        self.phase_ax.set_yticks(np.linspace(-np.pi, np.pi, 5))
        self.phase_ax.set_yticklabels([r"$-\pi$", r"$-\pi/2$", r"0", r"$\pi/2$", r"$\pi$"])

        self.fig.tight_layout()
        plt.ion()
        plt.show()

        config_builder = ConfigBuilder()
        config_builder.service = config_builder.SERVICE_IQ
        config_builder.range_start = range_start
        config_builder.range_length = range_end - range_start
        config_builder.sweep_frequency = 10
        config_builder.sweep_count = 2**16

        streaming_client = StreamingClient(args.host)
        streaming_client.run_session(config_builder.config, self.on_data)

    def on_data(self, metadata, payload):
        data = payload[0]
        amplitude = np.abs(data)
        phase = np.angle(data)

        max_amplitude = np.max(amplitude)
        if max_amplitude > self.amplitude_y_max:
            self.amplitude_y_max = max_amplitude
            self.ampl_ax.set_ylim(0, 1.1 * max_amplitude)

        if self.sweep_index == 0:
            plot_x = np.linspace(self.plot_x_min, self.plot_x_max, data.size)
            self.amplitude_line, = self.ampl_ax.plot(plot_x, amplitude)
            self.phase_line, = self.phase_ax.plot(plot_x, phase)
        else:
            self.amplitude_line.set_ydata(amplitude)
            self.phase_line.set_ydata(phase)

        self.fig.canvas.flush_events()

        self.sweep_index += 1
        return True


if __name__ == "__main__":
    IQMPLExample().run()
