from time import sleep

from acconeer.exptool.clients.reg.client import RegClient
from acconeer.exptool import utils


def main():
    args = utils.ExampleArgumentParser().parse_args()
    utils.config_logging(args)

    if args.socket_addr:
        raise Exception("Socket is not supported")
    elif args.spi:
        raise Exception("SPI is not supported")
    else:
        port = args.serial_port or utils.autodetect_serial_port()
        client = RegClient(port)

    client.connect()

    pin = RegClient._XM112_LED_PIN

    client._write_gpio(pin, 1)
    val = client._read_gpio(pin)
    print(val)

    for _ in range(3):
        sleep(0.1)
        client._write_gpio(pin, 0)  # on
        sleep(0.1)
        client._write_gpio(pin, 1)  # off

    client.disconnect()


if __name__ == "__main__":
    main()
