# Copyright (c) Acconeer AB, 2026
# All rights reserved

"""Tests for the Resource Calculator, exercised through its event broker."""

from __future__ import annotations

import typing as t

import pytest

from PySide6.QtWidgets import QDockWidget, QLabel, QWidget

from acconeer.exptool import a2, a121
from acconeer.exptool.a2.algo.heatmap import capon, coherent, conventional, robust_capon
from acconeer.exptool.a121.algo import distance, presence
from acconeer.exptool.app.new.ui.resource_tab.event_system import (
    BreakdownToggleEvent,
    ChangeIdEvent,
    EventBroker,
    IdentifiedServiceUninstalledEvent,
)
from acconeer.exptool.app.new.ui.resource_tab.services import (
    _a2_power_selections,
    a2_heatmap_capon_config_input,
    a2_heatmap_coherent_config_input,
    a2_heatmap_conventional_config_input,
    a2_heatmap_robust_capon_config_input,
    a2_session_config_input,
    a121_session_config_input,
    distance_config_input,
    memory_breakdown_output,
    power_consumption_vs_rate_output,
    power_curve_output,
    power_state_summary_output,
    presence_config_input,
)
from acconeer.exptool.app.new.ui.resource_tab.widgets import ResourceMainWidget


pytestmark = pytest.mark.usefixtures("qapplication")

InputFactory = t.Callable[[EventBroker], t.Any]

# Every input block the toolbar can spawn: how to build it, the service id it takes
# and the title of the dock it ends up in
_INPUT_BLOCKS = [
    (
        "a121_sparse_iq",
        a121.SessionConfig,
        lambda broker: a121_session_config_input.SessionConfigInput(broker, a121.SessionConfig()),
        "a121-sparse-iq-1",
        "A121 Sparse IQ config",
    ),
    (
        "distance",
        distance.DetectorConfig,
        lambda broker: distance_config_input.DistanceConfigInput(
            broker, distance.DetectorConfig()
        ),
        "distance-1",
        "Distance config",
    ),
    (
        "presence",
        presence.DetectorConfig,
        lambda broker: presence_config_input.PresenceConfigInput(
            broker, presence.DetectorConfig()
        ),
        "presence-1",
        "Presence config",
    ),
    (
        "a2_sparse_iq",
        a2.SessionConfig.default,
        lambda broker: a2_session_config_input.SessionConfigInput(
            broker, a2.SessionConfig.default()
        ),
        "a2-sparse-iq-1",
        "A2 Sparse IQ config",
    ),
    (
        "a2_capon",
        capon.HeatmapAndSessionConfig.default,
        lambda broker: a2_heatmap_capon_config_input.HeatmapCaponConfigInput(
            broker, capon.HeatmapAndSessionConfig.default()
        ),
        "a2-capon-1",
        "A2 Capon config",
    ),
    (
        "a2_coherent",
        coherent.HeatmapAndSessionConfig.default,
        lambda broker: a2_heatmap_coherent_config_input.HeatmapCoherentConfigInput(
            broker, coherent.HeatmapAndSessionConfig.default()
        ),
        "a2-coherent-1",
        "A2 Coherent config",
    ),
    (
        "a2_conventional",
        conventional.HeatmapAndSessionConfig.default,
        lambda broker: a2_heatmap_conventional_config_input.HeatmapConventionalConfigInput(
            broker, conventional.HeatmapAndSessionConfig.default()
        ),
        "a2-conventional-1",
        "A2 Conventional config",
    ),
    (
        "a2_robust_capon",
        robust_capon.HeatmapAndSessionConfig.default,
        lambda broker: a2_heatmap_robust_capon_config_input.HeatmapRobustCaponConfigInput(
            broker, robust_capon.HeatmapAndSessionConfig.default()
        ),
        "a2-robust-capon-1",
        "A2 Robust Capon config",
    ),
]

INPUTS = [
    pytest.param(input_factory, service_id, id=name)
    for name, _, input_factory, service_id, _ in _INPUT_BLOCKS
]

A2_INPUTS = [
    pytest.param(input_factory, service_id, id=name)
    for name, _, input_factory, service_id, _ in _INPUT_BLOCKS
    if service_id.startswith("a2-")
]

SPAWNABLE_CONFIGS = [
    pytest.param(config_factory, title, id=name)
    for name, config_factory, _, _, title in _INPUT_BLOCKS
]

assert len(A2_INPUTS) == 5, "the A2 inputs are the ones the power model covers"


@pytest.fixture
def broker() -> EventBroker:
    return EventBroker()


@pytest.fixture
def memory_output(broker: EventBroker) -> memory_breakdown_output.MemoryBreakdownOutput:
    return memory_breakdown_output.MemoryBreakdownOutput(broker)


@pytest.fixture
def power_output(broker: EventBroker) -> power_curve_output.EnergyRegionOutput:
    return power_curve_output.EnergyRegionOutput(broker)


@pytest.fixture
def outputs(
    broker: EventBroker,
    power_output: power_curve_output.EnergyRegionOutput,
    memory_output: memory_breakdown_output.MemoryBreakdownOutput,
) -> list[t.Any]:
    """The default loadout, plus the memory breakdown"""
    return [
        power_output,
        power_consumption_vs_rate_output.PowerConsumptionVsRateOutput(broker),
        power_state_summary_output.PowerStateSummaryOutput(broker),
        memory_output,
    ]


def _memory_row(
    output: memory_breakdown_output.MemoryBreakdownOutput, service_id: str
) -> list[str] | None:
    for line in output.toPlainText().splitlines():
        if line.startswith(f"{service_id} "):
            return line.split()

    return None


def _power_tab_titles(output: power_curve_output.EnergyRegionOutput) -> list[str]:
    return [output.tabText(i) for i in range(output.count())]


def _visible_docks(main_widget: ResourceMainWidget) -> list[QDockWidget]:
    """Closing a dock hides it, it stays a child of the window"""
    return [dock for dock in main_widget.findChildren(QDockWidget) if not dock.isHidden()]


def _dock_titles(main_widget: ResourceMainWidget) -> list[str]:
    return [dock.windowTitle() for dock in _visible_docks(main_widget)]


@pytest.mark.parametrize(("input_factory", "service_id"), INPUTS)
def test_input_shows_up_in_the_memory_breakdown(
    broker: EventBroker,
    outputs: list[t.Any],
    memory_output: memory_breakdown_output.MemoryBreakdownOutput,
    input_factory: InputFactory,
    service_id: str,
) -> None:
    input_factory(broker)

    row = _memory_row(memory_output, service_id)

    assert row is not None, memory_output.toPlainText()
    assert len(row) == 3
    # _fmt_number rounds up to the next multiple of 100, so 0 B renders as "100B"
    assert all(figure.endswith("B") and int(figure[:-1]) >= 200 for figure in row[1:])


@pytest.mark.parametrize(("input_factory", "service_id"), INPUTS)
def test_closing_an_input_cleans_up_the_outputs(
    broker: EventBroker,
    outputs: list[t.Any],
    memory_output: memory_breakdown_output.MemoryBreakdownOutput,
    power_output: power_curve_output.EnergyRegionOutput,
    input_factory: InputFactory,
    service_id: str,
) -> None:
    service = input_factory(broker)

    service.uninstall_function()

    assert _memory_row(memory_output, service_id) is None
    assert service_id not in _power_tab_titles(power_output)


@pytest.mark.parametrize(("input_factory", "service_id"), INPUTS)
def test_renaming_an_input_renames_its_memory_row(
    broker: EventBroker,
    outputs: list[t.Any],
    memory_output: memory_breakdown_output.MemoryBreakdownOutput,
    input_factory: InputFactory,
    service_id: str,
) -> None:
    input_factory(broker)
    row = _memory_row(memory_output, service_id)
    assert row is not None

    broker.offer_event(ChangeIdEvent(service_id, "renamed"))

    assert _memory_row(memory_output, service_id) is None
    assert _memory_row(memory_output, "renamed") == ["renamed", *row[1:]]


@pytest.mark.parametrize(("input_factory", "service_id"), A2_INPUTS)
def test_a2_input_gets_a_power_curve(
    broker: EventBroker,
    outputs: list[t.Any],
    power_output: power_curve_output.EnergyRegionOutput,
    input_factory: InputFactory,
    service_id: str,
) -> None:
    input_factory(broker)

    assert service_id in _power_tab_titles(power_output)


def test_uninstalling_an_untracked_service_is_ignored(
    outputs: list[t.Any],
    broker: EventBroker,
    memory_output: memory_breakdown_output.MemoryBreakdownOutput,
    power_output: power_curve_output.EnergyRegionOutput,
) -> None:
    """An output only cleans up what it has a tab for"""
    a2_heatmap_capon_config_input.HeatmapCaponConfigInput(
        broker, capon.HeatmapAndSessionConfig.default()
    )
    before = memory_output.toPlainText()

    broker.offer_event(IdentifiedServiceUninstalledEvent("never-installed-1"))

    assert memory_output.toPlainText() == before
    assert _power_tab_titles(power_output) == ["a2-capon-1"]


def test_an_output_added_late_catches_up(broker: EventBroker) -> None:
    """Outputs are briefed with the events they missed when they are added"""
    service = a2_heatmap_capon_config_input.HeatmapCaponConfigInput(
        broker, capon.HeatmapAndSessionConfig.default()
    )

    late_output = memory_breakdown_output.MemoryBreakdownOutput(broker)

    assert _memory_row(late_output, service.id_) is not None


@pytest.mark.parametrize(("config_factory", "title"), SPAWNABLE_CONFIGS)
def test_spawning_an_input_block_adds_a_dock(
    config_factory: t.Callable[[], t.Any], title: str
) -> None:
    """Covers the dispatch behind the toolbar buttons"""
    main_widget = ResourceMainWidget()

    main_widget.spawn_input_block(config_factory(), animate=False)

    assert title in _dock_titles(main_widget)


@pytest.mark.parametrize(("config_factory", "title"), SPAWNABLE_CONFIGS)
def test_closing_a_spawned_input_block(config_factory: t.Callable[[], t.Any], title: str) -> None:
    main_widget = ResourceMainWidget()
    main_widget.spawn_input_block(config_factory(), animate=False)
    matching = [d for d in _visible_docks(main_widget) if d.windowTitle() == title]

    assert len(matching) == 1, _dock_titles(main_widget)
    dock = matching[0]

    dock.close()

    assert title not in _dock_titles(main_widget)


def test_renaming_through_the_broker_keeps_ids_unique(
    broker: EventBroker,
    outputs: list[t.Any],
    memory_output: memory_breakdown_output.MemoryBreakdownOutput,
) -> None:
    """The ledger hands out a numbered id rather than letting two blocks share one"""
    first = a2_heatmap_capon_config_input.HeatmapCaponConfigInput(
        broker, capon.HeatmapAndSessionConfig.default()
    )
    second = a2_heatmap_coherent_config_input.HeatmapCoherentConfigInput(
        broker, coherent.HeatmapAndSessionConfig.default()
    )

    taken = broker.change_id(first.id_, second.id_)
    broker.offer_event(ChangeIdEvent(second.id_, taken))

    assert taken != first.id_
    assert _memory_row(memory_output, first.id_) is not None
    assert _memory_row(memory_output, taken) is not None


def test_invalid_config_is_shown_and_offered_to_nobody(
    broker: EventBroker,
    outputs: list[t.Any],
    memory_output: memory_breakdown_output.MemoryBreakdownOutput,
) -> None:
    """A heatmap takes one subsweep, and the editors have no field to put that on"""
    session_config = a2.SessionConfig(
        [a2.SensorConfig.identical_subsweeps(num_subsweeps=2)], update_rate=None
    )
    service = a2_heatmap_capon_config_input.HeatmapCaponConfigInput(
        broker,
        capon.HeatmapAndSessionConfig(
            session_config=session_config, heatmap_config=capon.HeatmapConfig.default()
        ),
    )

    service._display_validation_results()

    messages = [
        label.text()
        for label in service.misc_error_view.findChildren(QLabel)
        if label.text() and "Miscellaneous" not in label.text()
    ]

    assert messages == ["Heatmap processing takes exactly one subsweep"]
    assert _memory_row(memory_output, service.id_) is None


def test_toggling_the_current_breakdown(broker: EventBroker, outputs: list[t.Any]) -> None:
    a2_heatmap_capon_config_input.HeatmapCaponConfigInput(
        broker, capon.HeatmapAndSessionConfig.default()
    )

    broker.offer_event(BreakdownToggleEvent(False))
    broker.offer_event(BreakdownToggleEvent(True))


def test_every_power_selection_reaches_the_listener() -> None:
    """Each pidget carries its new value, the editor's signal carries none."""
    parent = QWidget()  # bound, or Qt collects it and the editor with it
    editor = _a2_power_selections.PowerSelectionsEditor(parent)
    updates = []
    editor.sig_update.connect(lambda: updates.append(1))

    for selection in (
        editor.aps_sleep_state_selection,
        editor.aps_idle_state_selection,
        editor.temperature_selection,
    ):
        selection.sig_update.emit(selection.get_data())

    assert len(updates) == 3


def test_every_toolbar_config_action_spawns_a_block() -> None:
    """The toolbar is the only place that names the blocks the user can add

    The output actions are left out, and so is Info, which opens a modal dialog.
    """
    main_widget = ResourceMainWidget()
    toolbar = main_widget.centralWidget()

    actions = [action for action in toolbar.actions() if action.text().startswith("New ")]

    assert len(actions) == len(SPAWNABLE_CONFIGS)

    for action in actions:
        action.trigger()

        name = action.text()[len("New ") :]

        assert any(title.endswith(name) for title in _dock_titles(main_widget)), name


def test_a2_power_vs_rate_leaves_the_offered_config_alone() -> None:
    """The config of an event is shared by every output that handles it"""
    config = a2.SessionConfig.default()
    config.sensor_config.inter_frame_idle_state = a2.IdleState.ARMED

    evolved = power_consumption_vs_rate_output._A2PowerConsumptionVsRatePlot._evolve_config(
        config, inter_frame_idle_state=a2.IdleState.READY
    )

    assert evolved.sensor_config.inter_frame_idle_state == a2.IdleState.READY
    assert config.sensor_config.inter_frame_idle_state == a2.IdleState.ARMED


def test_a_heatmap_with_an_invalid_session_config_is_offered_to_nobody(
    broker: EventBroker,
    outputs: list[t.Any],
    memory_output: memory_breakdown_output.MemoryBreakdownOutput,
) -> None:
    session_config = a2.SessionConfig.default()
    session_config.update_rate = 5.0
    session_config.sensor_config.frame_rate = 10.0
    with pytest.raises(a2.ValidationError):
        session_config.validate()

    service = a2_heatmap_capon_config_input.HeatmapCaponConfigInput(
        broker,
        capon.HeatmapAndSessionConfig(
            session_config=session_config, heatmap_config=capon.HeatmapConfig.default()
        ),
    )

    assert _memory_row(memory_output, service.id_) is None
