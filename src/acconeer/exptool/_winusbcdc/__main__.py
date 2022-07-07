import argparse
import logging
import msvcrt
import os
import threading

from winusbcdc import ComPort


try:
    import Queue as queue
except ImportError:
    import queue


def config_log():
    log = logging.getLogger("winusbcdc")
    if "PYTERMINAL_DEBUG" in os.environ:
        log.setLevel(logging.DEBUG)
        fileHandler = logging.FileHandler("terminal.log")
        log_fmt = logging.Formatter(
            "%(levelname)s %(name)s %(threadName)-10s " + "%(funcName)s() %(message)s"
        )
        fileHandler.setFormatter(log_fmt)
        log.addHandler(fileHandler)
    return log


log = config_log()

PRINTABLE_CHAR = set(list(range(ord(" "), ord("~") + 1)) + [ord("\r"), ord("\n")])


def getch():
    """Gets a single character from standard input.
    Does not echo to the screen.
    """
    return msvcrt.getch()


def configInputQueue():
    """configure a queue for accepting characters and return the queue"""

    def captureInput(iqueue):
        while True:
            c = getch()
            if c == "\x03" or c == "\x04":  # end on ctrl+c / ctrl+d
                log.debug("Break received (\\x{0:02X})".format(ord(c)))
                iqueue.put(c)
                break
            log.debug("Input Char '{}' received".format(c if c != "\r" else "\\r"))
            iqueue.put(c)

    input_queue = queue.Queue()
    input_thread = threading.Thread(target=lambda: captureInput(input_queue))
    input_thread.daemon = True
    input_thread.start()
    return input_queue, input_thread


def fmt_text(text):
    """convert characters that aren't printable to hex format"""
    newtext = ("\\x%02x" % c if c not in PRINTABLE_CHAR else chr(c) for c in text)
    textlines = "\r\n".join(l.strip("\r") for l in "".join(newtext).split("\n"))
    return textlines


def run_terminal(p: ComPort, log):
    log.info("Beginning a terminal run")
    p.setControlLineState(True, True)
    p.setLineCoding()

    q, t = configInputQueue()

    while True:
        read = p.read()
        if read:
            print(fmt_text(read), end="")

        if not q.empty():
            c = q.get()
            if c == "\x03" or c == "\x04":  # end on ctrl+c / ctrl+d
                print()
                p.disconnect()
                break
            try:
                p.write(c)
            except Exception as e:
                log.warn("USB Error on write {}".format(e))
                return


def main():
    parser = argparse.ArgumentParser(description="WinUSB Com Port")
    parser.add_argument("--name", help="USB Device name")
    parser.add_argument("--vid", help="USB Vendor ID")
    parser.add_argument("--pid", help="USB Product ID")

    args = parser.parse_args()

    p = ComPort(args.name, args.vid, args.pid)
    if p is None:
        exit()

    run_terminal(p, log)


if __name__ == "__main__":
    main()
