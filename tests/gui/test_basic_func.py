import pytest
import sys
import os
from PyQt5 import QtCore

sys.path.append(os.path.join(os.path.dirname(__file__), "../.."))  # noqa: E402
from gui.main import GUI
from gui.elements.modules import MODULE_INFOS


MOCK_INTERFACE = "Simulated"
LB = QtCore.Qt.LeftButton


@pytest.fixture
def gui(qtbot):
    w = GUI(under_test=True)
    qtbot.addWidget(w)
    with qtbot.waitExposed(w):
        w.show()
    return w


def test_select_interface(qtbot, gui):
    interfaces = [MOCK_INTERFACE, "SPI", MOCK_INTERFACE]
    for interface in interfaces:
        set_and_check_cb(qtbot, gui.interface_dd, interface)


def test_run_a_session(qtbot, gui):
    assert gui.buttons["connect"].text() == "Connect"
    assert not gui.buttons["start"].isEnabled()
    assert not gui.buttons["stop"].isEnabled()
    assert gui.statusBar().currentMessage() == "Not connected"

    set_and_check_cb(qtbot, gui.module_dd, "Envelope")
    set_and_check_cb(qtbot, gui.interface_dd, MOCK_INTERFACE)
    check_cb(qtbot, gui.module_dd, "Envelope")

    qtbot.mouseClick(gui.buttons["connect"], LB)
    expected_status = "Connected via simulated interface"
    qtbot.waitUntil(lambda: gui.statusBar().currentMessage() == expected_status)
    qtbot.waitUntil(lambda: gui.buttons["connect"].text() == "Disconnect")
    qtbot.waitUntil(lambda: gui.buttons["start"].isEnabled())
    qtbot.waitUntil(lambda: not gui.buttons["stop"].isEnabled())

    qtbot.mouseClick(gui.buttons["start"], LB)
    qtbot.wait(500)
    assert gui.threaded_scan.isRunning()
    assert not gui.buttons["start"].isEnabled()
    assert gui.buttons["stop"].isEnabled()

    with qtbot.waitSignal(gui.sig_scan) as sig:
        qtbot.mouseClick(gui.buttons["stop"], LB)

    assert sig.args[0] == "stop"

    qtbot.waitUntil(lambda: gui.buttons["start"].isEnabled())
    qtbot.waitUntil(lambda: not gui.buttons["stop"].isEnabled())

    qtbot.mouseClick(gui.buttons["connect"], LB)
    qtbot.waitUntil(lambda: gui.buttons["connect"].text() == "Connect")


def test_multi_sensor(qtbot, gui):
    assert len(gui.sensor_widgets["main"].checkboxes) == 4
    set_and_check_cb(qtbot, gui.interface_dd, MOCK_INTERFACE)  # allows multi

    set_and_check_cb(qtbot, gui.module_dd, "Envelope")  # allows multi
    qtbot.wait(200)

    for _ in range(2):
        qtbot.waitUntil(lambda: not gui.sensor_widgets["main"].textbox.isVisible())
        for checkbox in gui.sensor_widgets["main"].checkboxes.values():
            qtbot.waitUntil(lambda: checkbox.isVisible())

        connect_and_disconnect(qtbot, gui)

    set_and_check_cb(qtbot, gui.module_dd, "Presence detection (sparse)")  # doesn't allow multi
    qtbot.wait(200)

    for _ in range(2):
        qtbot.waitUntil(lambda: gui.sensor_widgets["main"].textbox.isVisible())
        for checkbox in gui.sensor_widgets["main"].checkboxes.values():
            qtbot.waitUntil(lambda: not checkbox.isVisible())

        connect_and_disconnect(qtbot, gui)


def test_start_and_stop_all_modules(qtbot, gui):
    set_and_check_cb(qtbot, gui.interface_dd, MOCK_INTERFACE)
    qtbot.mouseClick(gui.buttons["connect"], LB)

    for module_info in MODULE_INFOS:
        if module_info.module is None:
            continue

        set_and_check_cb(qtbot, gui.module_dd, module_info.label)
        qtbot.wait(200)

        qtbot.mouseClick(gui.buttons["start"], LB)
        qtbot.wait(600)
        qtbot.mouseClick(gui.buttons["stop"], LB)
        qtbot.wait(200)


def connect_and_disconnect(qtbot, gui):
    qtbot.mouseClick(gui.buttons["connect"], LB)
    qtbot.waitUntil(lambda: gui.buttons["connect"].text() == "Disconnect")
    qtbot.mouseClick(gui.buttons["connect"], LB)
    qtbot.waitUntil(lambda: gui.buttons["connect"].text() == "Connect")


def set_cb(cb, text):
    index = cb.findText(text, QtCore.Qt.MatchFixedString)
    assert index >= 0
    cb.setCurrentIndex(index)


def check_cb(qtbot, cb, text, timeout=1000):
    qtbot.waitUntil(lambda: cb.currentText() == text, timeout=timeout)


def set_and_check_cb(qtbot, cb, text, timeout=1000):
    set_cb(cb, text)
    check_cb(qtbot, cb, text, timeout=timeout)
