import multiprocessing
import sys
import time

import webbrowser
import threading
from server import http_server

from acconeer_utils.clients.reg.client import RegClient
from acconeer_utils.clients.json.client import JSONClient
from acconeer_utils.clients import configs
from acconeer_utils import example_utils


def check_connection(args):
    print("Checking connection to radar")
    try:
        if args.socket_addr:
            client = JSONClient(args.socket_addr)
        else:
            port = args.serial_port or example_utils.autodetect_serial_port()
            client = RegClient(port)

        config = configs.EnvelopeServiceConfig()
        client.connect()
        client.setup_session(config)
        client.disconnect()
        return True
    except Exception as e:
        print(e)
        return False


def open_browser_delayed():
    time.sleep(5)  # TODO: Add proper synchronization so we can be sure that the server has started

    webbrowser.open_new_tab("http://127.0.0.1:5000")


def main():
    args = example_utils.ExampleArgumentParser(num_sens=1).parse_args()
    example_utils.config_logging(args)

    if not check_connection(args):
        print("Please check connection to radar sensor module or streaming server")
        sys.exit(1)

    print("Please wait for the radar viewer to open your web browser...\n\n")

    threading.Thread(target=open_browser_delayed, args=()).start()
    http_server.start_server(args)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
