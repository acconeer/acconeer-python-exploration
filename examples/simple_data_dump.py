from acconeer_utils.streaming_client import StreamingClient
from acconeer_utils.config_builder import ConfigBuilder
from acconeer_utils.example_argparse import ExampleArgumentParser


class Main:
    def run(self):
        parser = ExampleArgumentParser()
        args = parser.parse_args()

        config_builder = ConfigBuilder()
        config_builder.range_start = 0.2
        config_builder.range_length = 0.1
        config_builder.sweep_count = 10

        streaming_client = StreamingClient(args.host)
        streaming_client.run_session(config_builder.config, self.on_data)

    def on_data(self, metadata, payload):
        data = payload[0]
        print()
        print(data)
        print()
        return True


if __name__ == "__main__":
    Main().run()
