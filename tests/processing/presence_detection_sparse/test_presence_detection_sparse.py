# Copyright (c) Acconeer AB, 2022
# All rights reserved

import site
from pathlib import Path

from acconeer.exptool._tests.test_rig import ProcessingTestModule
from acconeer.exptool.a111.algo.presence_detection_sparse._processor import (
    ProcessingConfiguration,
    Processor,
)


processing_dir = Path(__file__).parents[3] / "examples" / "processing"  # noqa: E402
site.addsitedir(processing_dir)  # noqa: E402


HERE = Path(__file__).parent

TEST_KEYS = ["presence_score", "depthwise_presence"]
PARAMETER_SETS = [
    {},
    {"num_removed_pc": 1},
    {"num_removed_pc": 2},
]

test_module = ProcessingTestModule(
    Processor,
    ProcessingConfiguration,
    HERE,
    TEST_KEYS,
    PARAMETER_SETS,
)


def test_all():
    test_module.run_all_tests()


if __name__ == "__main__":
    test_module.main()
