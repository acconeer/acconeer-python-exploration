# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved

import os
import sys
import tempfile
import typing as t
from pathlib import Path

import pytest

import acconeer.exptool.testing
from acconeer.exptool._artifact_repository import (
    ACCEPTED_DIGESTS,
    UnexpectedAlgoBundleError,
    install_algo_bundle,
)
from acconeer.exptool._processes.start_method import avoid_fork


PYTEST_XDIST_MAX_NUM_PROCESSES = 4

ALGO_BUNDLE_EXTRACT_DIR = pytest.StashKey[Path]()

sys.path.append(os.path.join(os.path.dirname(__file__), "helpers"))


# When the user passes --plot-show / --plot-show-on-fail, switch matplotlib to
# a windowed backend before any test module imports pyplot. The hatch test env
# sets QT_QPA_PLATFORM=offscreen so headless CI can use a Qt backend without a
# display; left alone, that makes plt.show() block forever on a window the user
# can never interact with.
_PLOT_FLAGS = ("--plot-show", "--plot-show-on-fail")
if any(arg in sys.argv for arg in _PLOT_FLAGS):
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        os.environ.pop("QT_QPA_PLATFORM")
    import matplotlib

    matplotlib.use("QtAgg", force=True)


def pytest_xdist_auto_num_workers(config: t.Any) -> int:
    # This hook is called for both pytest-xdists's "-n auto" and "-n logical" [1].
    #   Hatch's documentation indicates that only "-n logical" is used [2], but lets
    # cap all the number of cores in both cases.
    #
    # [1] https://pytest-xdist.readthedocs.io/en/latest/reference.html#pytest_xdist_auto_num_workers
    # [2] https://hatch.pypa.io/dev/tutorials/testing/overview/#parallelize-test-execution
    num_cpus = os.cpu_count() or 1
    return min(num_cpus, PYTEST_XDIST_MAX_NUM_PROCESSES)


def pytest_configure(config: pytest.Config) -> None:
    avoid_fork(preload=["acconeer.exptool.app.new.backend"])

    zip_path = config.getoption("--algo-bundle")
    if zip_path is not None:
        bundle_dir = tempfile.TemporaryDirectory(prefix="algo_bundle_")
        config.add_cleanup(bundle_dir.cleanup)
        extract_dir = Path(bundle_dir.name) / "extracted"
        skip_integrity_check = config.getoption("--dangerously-skip-integrity-check")
        try:
            install_algo_bundle(
                zip_path,
                extract_dir,
                accepted_digests=None if skip_integrity_check else ACCEPTED_DIGESTS,
            )
        except UnexpectedAlgoBundleError as e:
            msg = (
                f"{e.zip_path} (SHA-256 {e.digest}) is not the algo bundle this "
                "release accepts. Pass the accepted bundle to --algo-bundle, or pass "
                "--dangerously-skip-integrity-check to test a bundle of your own"
            )
            raise pytest.UsageError(msg) from e
        config.stash[ALGO_BUNDLE_EXTRACT_DIR] = extract_dir


def _has_plugin_needing_algo_bundle(item: pytest.Item) -> bool:
    callspec = getattr(item, "callspec", None)
    params = callspec.params.values() if callspec is not None else []
    return any(getattr(p, "requires_algo_bundle_artifact", False) is True for p in params)


def _validate_parametrization(iterable: t.Sized, err_msg: str) -> t.Sized:
    if acconeer.exptool.testing.is_running_in_ci() and len(iterable) < 1:
        raise ValueError(err_msg)
    return iterable


def pytest_generate_tests(metafunc):
    # This function dynamically parametrizes tests/fixtures based on CLI arguments.
    # See https://docs.pytest.org/en/latest/how-to/parametrize.html#basic-pytest-generate-tests-example

    err_msg_fmt = "Need to specify at least 1 {} when running in Jenkins."

    if "a111_exploration_server_path" in metafunc.fixturenames:
        # A111 testing could be left out when running sanity tests
        values = list(metafunc.config.getoption("--a111-exploration-server-paths", []))
        metafunc.parametrize(
            argnames="a111_exploration_server_path", argvalues=values, scope="session"
        )

    if "a121_exploration_server_path" in metafunc.fixturenames:
        values = _validate_parametrization(
            metafunc.config.getoption("--a121-exploration-server-paths", []),
            err_msg=err_msg_fmt.format("A121 Exploration Server"),
        )
        # scope="session": the fuzzing exploration server fixtures are
        # session-scoped and depend on this path.
        metafunc.parametrize(
            argnames="a121_exploration_server_path", argvalues=values, scope="session"
        )

    if "a2_exploration_server_path" in metafunc.fixturenames:
        values = _validate_parametrization(
            metafunc.config.getoption("--a2-exploration-server-paths", []),
            err_msg=err_msg_fmt.format("A2 Exploration Server"),
        )
        # scope="session": the fuzzing exploration server fixtures are
        # session-scoped and depend on this path.
        metafunc.parametrize(
            argnames="a2_exploration_server_path", argvalues=values, scope="session"
        )

    if "sensor_current_limits_path" in metafunc.fixturenames:
        values = _validate_parametrization(
            metafunc.config.getoption("--sensor-current-limits-path", []),
            err_msg=err_msg_fmt.format("A121 sensor current limits"),
        )
        metafunc.parametrize(
            argnames="sensor_current_limits_path", argvalues=values, scope="session"
        )

    if "module_current_limits_path" in metafunc.fixturenames:
        values = _validate_parametrization(
            metafunc.config.getoption("--module-current-limits-path", []),
            err_msg=err_msg_fmt.format("A121 module current limits"),
        )
        metafunc.parametrize(
            argnames="module_current_limits_path", argvalues=values, scope="session"
        )

    if "inter_sweep_idle_state_current_limits_path" in metafunc.fixturenames:
        values = _validate_parametrization(
            metafunc.config.getoption("--inter-sweep-idle-state-current-limits-path", []),
            err_msg=err_msg_fmt.format("A121 inter sweep idle state current limits"),
        )
        metafunc.parametrize(
            argnames="inter_sweep_idle_state_current_limits_path",
            argvalues=values,
            scope="session",
        )

    if "memory_usage_path" in metafunc.fixturenames:
        values = _validate_parametrization(
            metafunc.config.getoption("--memory-usage-path", []),
            err_msg=err_msg_fmt.format("A121 memory usage"),
        )
        metafunc.parametrize(argnames="memory_usage_path", argvalues=values, scope="session")

    if "a2_sensor_current_limits_path" in metafunc.fixturenames:
        values = _validate_parametrization(
            metafunc.config.getoption("--a2-sensor-current-limits-path", []),
            err_msg=err_msg_fmt.format("A2 sensor current limits"),
        )
        metafunc.parametrize(
            argnames="a2_sensor_current_limits_path", argvalues=values, scope="session"
        )

    if "a2_timing_limits_path" in metafunc.fixturenames:
        values = _validate_parametrization(
            metafunc.config.getoption("--a2-timing-limits-path", []),
            err_msg=err_msg_fmt.format("A2 timing limits"),
        )
        metafunc.parametrize(argnames="a2_timing_limits_path", argvalues=values, scope="session")

    if "a2_computation_time_limits_path" in metafunc.fixturenames:
        values = _validate_parametrization(
            metafunc.config.getoption("--a2-computation-time-limits-path", []),
            err_msg=err_msg_fmt.format("A2 computation time limits"),
        )
        metafunc.parametrize(
            argnames="a2_computation_time_limits_path", argvalues=values, scope="session"
        )

    if "a2_memory_usage_path" in metafunc.fixturenames:
        values = _validate_parametrization(
            metafunc.config.getoption("--a2-memory-usage-path", []),
            err_msg=err_msg_fmt.format("A2 memory usage"),
        )
        metafunc.parametrize(argnames="a2_memory_usage_path", argvalues=values, scope="session")


def pytest_collection_modifyitems(config, items):
    skip_algo_bundle_marker = pytest.mark.skip(
        reason="Needs the algo bundle, pass '--algo-bundle <zip>'"
    )
    for item in items:
        if _has_plugin_needing_algo_bundle(item):
            item.add_marker(pytest.mark.algo_bundle)
        if "algo_bundle" in item.keywords and config.getoption("--algo-bundle") is None:
            item.add_marker(skip_algo_bundle_marker)

    if config.getoption("--test-devsite"):
        return  # Don't skip any devsite tests

    skip_devsite_marker = pytest.mark.skip(reason="Needs '--test-devsite' to run")
    for item in items:
        if "devsite" in item.keywords:
            item.add_marker(skip_devsite_marker)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    result = outcome.get_result()
    setattr(item, f"rep_{result.when}", result)


@pytest.fixture(scope="session")
def algo_bundle_extract_dir(request: pytest.FixtureRequest) -> Path | None:
    """Where the algo bundle was installed to, for backend processes to import it from"""
    return request.config.stash.get(ALGO_BUNDLE_EXTRACT_DIR, None)


@pytest.fixture(scope="session")
def should_update_outputs(request):
    return request.config.getoption("--update-outputs") is True


@pytest.fixture(scope="session")
def is_running_in_ci() -> bool:
    return acconeer.exptool.testing.is_running_in_ci()


def _plot_show_enabled(request: pytest.FixtureRequest) -> bool:
    return bool(
        request.config.getoption("--plot-show") or request.config.getoption("--plot-show-on-fail")
    )


@pytest.fixture
def plot_show_enabled(request) -> bool:
    """True when --plot-show or --plot-show-on-fail was passed.

    Tests guard their plotting block on this so the matplotlib import only
    happens when the user asked for plots:

        def test_foo(plot_figures, plot_show_enabled):
            ...  # main test logic
            if plot_show_enabled:
                import matplotlib.pyplot as plt
                fig, ax = plt.subplots()
                ...
                plot_figures.append(fig)
    """
    return _plot_show_enabled(request)


@pytest.fixture
def plot_figures(request):
    """Collect figures built by a test and show/close them based on CLI flags.

    Figures are shown when --plot-show is passed, or when the test fails (in
    setup or call) and --plot-show-on-fail is passed. Otherwise figures are
    closed at teardown. The fixture itself never imports matplotlib — that is
    the test body's responsibility, guarded by ``plot_show_enabled``.
    """
    figures: list = []
    yield figures

    if not _plot_show_enabled(request):
        return

    import matplotlib.pyplot as plt

    show_always = request.config.getoption("--plot-show")
    show_on_fail = request.config.getoption("--plot-show-on-fail")

    def _failed(when: str) -> bool:
        rep = getattr(request.node, f"rep_{when}", None)
        return rep is not None and rep.failed

    failed = _failed("setup") or _failed("call")

    if show_always or (show_on_fail and failed):
        plt.show()
    else:
        plt.close("all")
