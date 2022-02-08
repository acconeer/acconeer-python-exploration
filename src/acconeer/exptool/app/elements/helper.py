import enum
import os
import sys
from argparse import ArgumentParser


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


class ExptoolArgumentParser(ArgumentParser):
    def __init__(self):
        super().__init__()
        self.add_argument(
            "--purge-config",
            action="store_true",
            help="Remove Exptool-related files interactively.",
        )
        self.add_argument(
            "--no-config",
            action="store_false",
            dest="use_last_config",
            help="Runs Exptool without loading or saving gui configuration.",
        )
