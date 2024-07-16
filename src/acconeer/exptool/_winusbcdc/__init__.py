import os


if os.name == "nt":
    from .usb_cdc import ComPort
    from .winusb import *
    from .winusbpy import *
else:
    msg = "WinUsbPy only works on Windows platform"
    raise ImportError(msg)
