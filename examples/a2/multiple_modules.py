# Copyright (c) Acconeer AB, 2024-2026
# All rights reserved

from __future__ import annotations

from acconeer.exptool import a2


###############################################################################
# For auto detection of the connected modules you can use the following code:
#
# from acconeer.exptool import get_usb_devices
#
# usb_devices = get_usb_devices()
#
# if not usb_devices:
#     print("No USB devices available")
# else:
#     print("USB devices detected:")
#     print("".join([f" - {dev}\n" for dev in usb_devices]))
#
#     clients = {}
#     for dev in usb_devices:
#         # Only use XE212
#         if dev.name == "XE212":
#             clients[dev.serial] = a2.Client.open(usb_device=dev.serial)
###############################################################################

# Get the list of connected modules from command line:
#
# $ python -m acconeer.exptool.flash list
# == USB Devices ==
#  - XE212: USB_VID=0xacc0, USB_PID=0xa561 serial=353934643330
#  - XE212: USB_VID=0xacc0, USB_PID=0xa561 serial=384435543231

clients = {}
clients["353934643330"] = a2.Client.open(usb_device="353934643330")
clients["384435543231"] = a2.Client.open(usb_device="384435543231")

# Start session for all connected modules
for client in clients.values():
    client.setup_session(a2.SessionConfig.default())
    client.start_session()

# Get data for all connected modules and print the tick value for each:
for _ in range(5):
    for serial, client in clients.items():
        result = client.get_next()
        print(f"[{serial}] - client tick:", result.tick)

# Stop session and disconnect all modules
for client in clients.values():
    client.stop_session()
    client.close()

# This is what the output will be for two connected modules
#
# $ python examples/a2/multiple_modules.py
#
# [353934643330] - client tick: 33745
# [384435543231] - client tick: 23873
# [353934643330] - client tick: 33757
# [384435543231] - client tick: 23890
# [353934643330] - client tick: 33960
# [384435543231] - client tick: 23907
# [353934643330] - client tick: 33978
# [384435543231] - client tick: 23924
# [353934643330] - client tick: 33994
# [384435543231] - client tick: 23941
