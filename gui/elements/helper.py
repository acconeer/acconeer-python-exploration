import enum
import os
import sys

import acconeer.exptool


def lib_version_up_to_date(gui_handle=None):
    fdir = os.path.dirname(os.path.realpath(__file__))
    fn = os.path.join(fdir, "../../src/acconeer/exptool/__init__.py")
    if os.path.isfile(fn):
        with open(fn, "r") as f:
            lines = [line.strip() for line in f.readlines()]

        for line in lines:
            if line.startswith("__version__"):
                fs_lib_ver = line.split("=")[1].strip()[1:-1]
                break
        else:
            fs_lib_ver = None
    else:
        fs_lib_ver = None

    used_lib_ver = getattr(acconeer.exptool, "__version__", None)

    rerun_text = "You probably need to reinstall the library (python -m pip install -U --user .)"
    error_text = None
    if used_lib_ver:
        sb_text = "Lib v{}".format(used_lib_ver)

        if fs_lib_ver != used_lib_ver:
            sb_text += " (mismatch)"
            error_text = "Lib version mismatch."
            error_text += " Installed: {} Latest: {}\n".format(used_lib_ver, fs_lib_ver)
            error_text += rerun_text
    else:
        sb_text = "Lib version unknown"
        error_text = "Could not read installed lib version" + rerun_text

    if gui_handle is not None:
        gui_handle.labels["libver"].setText(sb_text)
        if error_text and sys.executable.endswith("pythonw.exe"):
            gui_handle.error_message(error_text)
    else:
        if not sys.executable.endswith("pythonw.exe") and error_text:
            prompt = "\nThe GUI might not work properly!\nContinue anyway? [y/N]"
            while True:
                print(error_text + prompt)
                choice = input().lower()
                if choice.lower() == "y":
                    return True
                elif choice == "" or choice.lower() == "n":
                    return False
                else:
                    sys.stdout.write("Please respond with 'y' or 'n' (or 'Y' or 'N').\n")
        return True


class LoadState(enum.Enum):
    UNLOADED = enum.auto()
    BUFFERED = enum.auto()
    LOADED = enum.auto()


class ErrorFormater:
    def __init__(self):
        pass

    def error_to_text(self, error):
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        err_text = "File: {}<br>Line: {}<br>Error: {}".format(fname, exc_tb.tb_lineno, error)

        return err_text


class PassthroughProcessor:
    def __init__(self, sensor_config, processing_config, session_info):
        pass

    def process(self, data, data_info):
        return data


class Count:
    def __init__(self, val=0):
        self.val = val

    def pre_incr(self):
        self.val += 1
        return self.val

    def post_incr(self):
        ret = self.val
        self.val += 1
        return ret

    def decr(self, val=1):
        self.val -= val

    def set_val(self, val):
        self.val = val
