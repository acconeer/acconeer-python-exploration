import pytest
import sys
import os
from PyQt5 import QtCore

sys.path.append(os.path.join(os.path.dirname(__file__), "../.."))  # noqa: E402
from gui.main import GUI


MOCK_INTERFACE = "Simulated"
STD_DELAY = 50
LB = QtCore.Qt.LeftButton


@pytest.fixture
def gui(qtbot):
    w = GUI()
    qtbot.addWidget(w)
    qtbot.waitForWindowShown(w)
    return w


def test_run_a_session(qtbot, gui):
    assert gui.buttons["connect"].text() == "Connect"
    assert not gui.buttons["start"].isEnabled()
    assert not gui.buttons["stop"].isEnabled()
    assert gui.statusBar().currentMessage() == "Not connected"

    qtbot.keyClicks(gui.module_dd, "Envelope", delay=STD_DELAY)

    assert gui.module_dd.currentText() == "Envelope"

    qtbot.keyClicks(gui.interface_dd, MOCK_INTERFACE, delay=STD_DELAY)

    assert gui.interface_dd.currentText() == MOCK_INTERFACE
    assert gui.module_dd.currentText() == "Envelope"

    qtbot.mouseClick(gui.buttons["connect"], LB, delay=STD_DELAY)

    assert gui.statusBar().currentMessage() == "Connected via simulated interface"
    assert gui.buttons["connect"].text() == "Disconnect"
    assert gui.buttons["start"].isEnabled()
    assert not gui.buttons["stop"].isEnabled()

    qtbot.mouseClick(gui.buttons["start"], LB, delay=STD_DELAY)

    assert not gui.buttons["start"].isEnabled()
    assert gui.buttons["stop"].isEnabled()

    qtbot.wait(200)

    assert gui.threaded_scan.isRunning()

    with qtbot.waitSignal(gui.sig_scan) as sig:
        qtbot.mouseClick(gui.buttons["stop"], LB, delay=STD_DELAY)

    assert sig.args[0] == "stop"
    assert gui.buttons["start"].isEnabled()
    assert not gui.buttons["stop"].isEnabled()

    qtbot.mouseClick(gui.buttons["connect"], LB, delay=STD_DELAY)

    assert gui.buttons["connect"].text() == "Connect"
