import site
from pathlib import Path

from acconeer.exptool._tests.test_rig import ProcessingTestModule
from acconeer.exptool.a111.algo.sleep_breathing._processor import (
    ProcessingConfiguration,
    Processor,
)


processing_dir = Path(__file__).parents[3] / "examples" / "processing"  # noqa: E402
site.addsitedir(processing_dir)  # noqa: E402


HERE = Path(__file__).parent

TEST_KEYS = ["f_dft_est", "f_est", "snr"]
PARAMETER_SETS = [
    {},
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
