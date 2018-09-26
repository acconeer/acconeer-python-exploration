import numpy as np

from acconeer_utils.streaming_client import StreamingClient
from acconeer_utils.config_builder import ConfigBuilder
from acconeer_utils.example_argparse import ExampleArgumentParser
from acconeer_utils.mpl_process import PlotProcess, FigureUpdater, PlotProccessDiedException


class IQMPLProcessExample:
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
        fig_updater = IQMPLProcessExampleFigureUpdater(plot_xlim)
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
            self.lowpass_sweep = np.array(sweep)  # create a copy
        else:
            alpha = 0.8
            self.lowpass_sweep = alpha*self.lowpass_sweep + (1-alpha)*sweep

        plot_data = {
            "ampl": np.abs(self.lowpass_sweep),
            "phase": np.angle(self.lowpass_sweep),
        }

        self.plot_process.put_data(plot_data)
        self.sweep_index += 1
        return True


class IQMPLProcessExampleFigureUpdater(FigureUpdater):
    def __init__(self, plot_xlim):
        self.plot_xlim = plot_xlim

    def setup(self, fig):
        self.axs = {
            "ampl": fig.add_subplot(2, 1, 1),
            "phase": fig.add_subplot(2, 1, 2),
        }

        self.axs["ampl"].set_title("Amplitude")
        self.axs["ampl"].set_xlabel("Depth (cm)")
        self.axs["ampl"].set_xlim(self.plot_xlim)
        self.axs["ampl"].set_ylim(0, 2000)

        self.axs["phase"].set_title("Phase")
        self.axs["phase"].set_xlabel("Depth (cm)")
        self.axs["phase"].set_xlim(self.plot_xlim)
        self.axs["phase"].set_ylim(-np.pi, np.pi)
        self.axs["phase"].set_yticks(np.linspace(-np.pi, np.pi, 5))
        self.axs["phase"].set_yticklabels([r"$-\pi$", r"$-\pi/2$", r"0", r"$\pi/2$", r"$\pi$"])

        for ax in self.axs.values():
            ax.grid(True)

        fig.canvas.set_window_title("Acconeer IQ data example")
        fig.set_size_inches(10, 7)
        fig.tight_layout()

    def first(self, d):
        range_xs = np.linspace(*self.plot_xlim, len(d["ampl"]))

        self.arts = {}
        for key, ys in d.items():
            self.arts[key] = self.axs[key].plot(range_xs, ys)[0]

        return self.arts.values()

    def update(self, d):
        for key, art in self.arts.items():
            art.set_ydata(d[key])


if __name__ == "__main__":
    IQMPLProcessExample().run()
