# Copyright (c) Acconeer AB, 2022
# All rights reserved

"""Internal tool for updating the register map YAML file

Requirements: PyYAML and oyaml

Quick install:
python -m pip install --user pyyaml oyaml

Usage:
python update_regmap.py /path/to/sw-main/module_server/register_map/register_map.yaml
"""

import argparse
import importlib.util
import os

import oyaml as yaml


here = os.path.dirname(os.path.realpath(__file__))
exptool_package_path = os.path.join(here, "..", "src", "acconeer", "exptool")

modes_module_path = os.path.join(exptool_package_path, "modes.py")
modes_module_spec = importlib.util.spec_from_file_location(
    "acconeer.exptool.modes", modes_module_path
)
modes_module = importlib.util.module_from_spec(modes_module_spec)
modes_module_spec.loader.exec_module(modes_module)

parser = argparse.ArgumentParser()
parser.add_argument("input_filename")
args = parser.parse_args()
in_fn = args.input_filename

out_fn = os.path.join(exptool_package_path, "data", "regmap.yaml")
assert os.path.exists(os.path.dirname(out_fn))

with open(in_fn, "r") as in_f:
    d = yaml.full_load(in_f)


def clean(d):
    to_pop = []

    for k, v in d.items():
        if k == "description":
            to_pop.append(k)
            continue

        if type(v) == dict:
            if v.get("internal", False):
                to_pop.append(k)
                continue

            if "modes" in v:
                modes = v["modes"]
                assert isinstance(modes, (list, str))
                if isinstance(modes, str):
                    modes = [modes]

                for mode in modes[:]:
                    try:
                        modes_module.get_mode(mode)
                    except ValueError:
                        modes.remove(mode)

                if len(modes) == 0:
                    to_pop.append(k)
                    continue

                v["modes"] = modes

            clean(v)

    for k in to_pop:
        d.pop(k)


clean(d)

with open(out_fn, "w") as out_f:
    yaml.dump(d, out_f, default_flow_style=False)
