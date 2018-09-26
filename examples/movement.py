import numpy as np
from matplotlib.gridspec import GridSpec

from acconeer_utils.streaming_client import StreamingClient
from acconeer_utils.config_builder import ConfigBuilder
from acconeer_utils.example_argparse import ExampleArgumentParser
from acconeer_utils.mpl_process import PlotProcess, FigureUpdater, PlotProccessDiedException


class MovementExample:
    def run(self):
        parser = ExampleArgumentParser()
        args = parser.parse_args()

        range_start = 0.2
        range_end = 0.8

        config_builder = ConfigBuilder()
        config_builder.service = ConfigBuilder.SERVICE_IQ
        config_builder.range_start = range_start
        config_builder.range_length = range_end - range_start
        config_builder.sweep_frequency = 80
        config_builder.sweep_count = 2**16
        config_builder.gain = 0.7

        self.sweep_index = 0
        self.total_movement_history = np.zeros(5*config_builder.sweep_frequency)

        plot_xlim = (int(100 * range_start + 0.5), int(100 * range_end + 0.5))
        fig_updater = MovementExampleFigureUpdater(plot_xlim)
        self.plot_process = PlotProcess(fig_updater)
        streaming_client = StreamingClient(args.host)

        self.plot_process.start()
        try:
            streaming_client.run_session(config_builder.config, self.on_data)
        except PlotProccessDiedException:
            pass
        self.plot_process.close()

    def on_data(self, metadata, payload):
        sweep = payload[0]

        if self.sweep_index == 0:
            self.slow_lowpass_sweep = np.array(sweep)
            self.fast_lowpass_sweep = np.array(sweep)
            self.lowpass_movement = np.zeros(len(sweep))

        slow_alpha = 0.02
        fast_alpha = 0.20
        movement_alpha = 0.005

        self.slow_lowpass_sweep = slow_alpha*sweep + (1-slow_alpha)*self.slow_lowpass_sweep
        self.fast_lowpass_sweep = fast_alpha*sweep + (1-fast_alpha)*self.fast_lowpass_sweep
        abs_diff = np.abs(self.slow_lowpass_sweep - self.fast_lowpass_sweep)
        movement = abs_diff**2 / 5000
        self.lowpass_movement = movement_alpha*movement + (1-movement_alpha)*self.lowpass_movement

        total_movement = np.sum(self.lowpass_movement) / 300
        total_movement = np.tanh(total_movement)  # soft limit to 1
        self.total_movement_history = np.roll(self.total_movement_history, -1)
        self.total_movement_history[-1] = total_movement

        plot_data = {
            "slow": abs(self.slow_lowpass_sweep),
            "fast": abs(self.fast_lowpass_sweep),
            "move": np.tanh(self.lowpass_movement),
            "history": self.total_movement_history,
        }

        self.plot_process.put_data(plot_data)

        self.sweep_index += 1
        return True


class MovementExampleFigureUpdater(FigureUpdater):
    def __init__(self, plot_xlim):
        self.plot_xlim = plot_xlim

    def setup(self, fig):
        self.fig = fig

        gs = GridSpec(2, 2)

        self.axs = {
            "ampl": fig.add_subplot(gs[0, 0]),
            "move_sweep": fig.add_subplot(gs[0, 1]),
            "history": fig.add_subplot(gs[1, :]),
        }

        self.axs["ampl"].set_title("Amplitude")
        self.axs["ampl"].set_xlabel("Depth (cm)")
        self.axs["ampl"].set_xlim(self.plot_xlim)
        self.axs["ampl"].set_ylim(0, 2000)

        self.axs["move_sweep"].set_title("Movement")
        self.axs["move_sweep"].set_xlabel("Depth (cm)")
        self.axs["move_sweep"].set_xlim(self.plot_xlim)
        self.axs["move_sweep"].set_ylim(0, 1)

        self.axs["history"].set_title("Total movement history")
        self.axs["history"].set_xlabel("Time (s)")
        self.axs["history"].set_xlim(-5, 0)
        self.axs["history"].set_ylim(0, 1)

        for ax in self.axs.values():
            ax.grid(True)

        fig.canvas.set_window_title("Acconeer movement example")
        fig.set_size_inches(10, 7)
        fig.tight_layout()

    def first(self, d):
        range_xs = np.linspace(*self.plot_xlim, len(d["fast"]))
        history_xs = np.linspace(-5, 0, len(d["history"]))

        self.arts = {
            "fast": self.axs["ampl"].plot(range_xs, d["fast"], animated=True)[0],
            "slow": self.axs["ampl"].plot(range_xs, d["slow"], animated=True)[0],
            "move": self.axs["move_sweep"].plot(range_xs, d["move"], animated=True)[0],
            "history": self.axs["history"].plot(history_xs, d["history"], animated=True)[0],
        }
        self.fig.canvas.draw()
        return self.arts.values()

    def update(self, d):
        for key, art in self.arts.items():
            art.set_ydata(d[key])


if __name__ == "__main__":
    MovementExample().run()
