# Copyright (c) Acconeer AB, 2022
# All rights reserved

try:
    import acconeer.exptool as et

    et_ver = et.__version__
except ImportError:
    et_ver = None

SEPARATOR = "-" * 65

print(SEPARATOR)
print("Acconeer Exploration Tool is no longer run from `gui/main.py` since v4.")
print()
print(f"Installed version: {et_ver}")
print(SEPARATOR)

if et_ver is None or not et_ver.startswith("4"):
    print("Install Acconeer Exploration Tool v4 with:")
    print()
    print("    python -m pip install --upgrade acconeer-exptool[app]")
    print()
    print("    -- or --")
    print()
    print("    python -m pip .[app] (while standing in the root directory of the repository.)")
    print()
    print("And then run the app with")
    print()
    print("    python -m acconeer.exptool.app")
    print()
    print("Read more here: https://docs.acconeer.com/")
else:
    print("Acconeer Exploration Tool v4 is installed. Run it with:")
    print()
    print("    python -m acconeer.exptool.app")

print(SEPARATOR)
print("If you are using the portable install of Exploration Tool,")
print("please download the new version available at:")
print()
print("    https://github.com/acconeer/acconeer-python-exploration#quickstart-for-windows")
print(SEPARATOR)
