from argparse import ArgumentParser


class ExampleArgumentParser(ArgumentParser):
    def __init__(self):
        super().__init__()

        self.add_argument(
            "host",
            help="The ip/hostname of your streaming server"
        )
        self.add_argument(
            "sensor",
            type=int,
            default=1,
            nargs="?",
            help="The port in which the sensor is mounted, default is 1"
        )
