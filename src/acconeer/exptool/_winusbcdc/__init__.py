import os


if os.name == "nt":
    from .usb_cdc import ComPort
    from .winusb import *
    from .winusbpy import *
else:
    raise ImportError("WinUsbPy only works on Windows platform")
