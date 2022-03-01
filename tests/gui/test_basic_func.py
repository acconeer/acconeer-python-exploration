import pytest
import requests

from PySide6 import QtCore

from acconeer.exptool.app import GUI
from acconeer.exptool.app.elements.modules import MODULE_INFOS


MOCK_INTERFACE = "Simulated"
LB = QtCore.Qt.LeftButton


def _have_internet_connection():
    try:
        requests.get("https://www.google.com")
        return True
    except requests.exceptions.ConnectionError:
        return False


def _get_gui(qtbot):
    w = GUI(under_test=True)
    qtbot.addWidget(w)
    with qtbot.waitExposed(w):
        w.show()
    return w


@pytest.fixture
def gui(qtbot):
    return _get_gui(qtbot)


@pytest.fixture
def mock_handler_gui(qtbot, mocker):
    """
    Not really interested if the webpage opens in a tab that is the module `webbrowser`'s
    responsibility. We are, however, interested whether the url will resolve (response.ok == True)
    """

    def mock_help_button_handler(self):
        # self == GUI
        url = self.current_module_info.docs_url
        if url:
            response = requests.get(url)
            self.under_test_help_button_response = response
        else:
            self.under_test_help_button_response = None

    mocker.patch("acconeer.exptool.app.GUI.service_help_button_handler", mock_help_button_handler)
    return _get_gui(qtbot)


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
    pass  # TODO


def test_start_and_stop_all_modules(qtbot, gui):
    set_and_check_cb(qtbot, gui.interface_dd, MOCK_INTERFACE)
    qtbot.mouseClick(gui.buttons["connect"], LB)

    for module_info in MODULE_INFOS:
        set_and_check_cb(qtbot, gui.module_dd, module_info.label)
        qtbot.wait(200)

        qtbot.mouseClick(gui.buttons["start"], LB)
        qtbot.wait(600)
        qtbot.mouseClick(gui.buttons["stop"], LB)
        qtbot.wait(200)


@pytest.mark.skipif(not _have_internet_connection(), reason="No internet connection")
def test_help_button_with_urls(qtbot, mock_handler_gui):
    for module_info in MODULE_INFOS:
        if not module_info.docs_url:
            continue
        set_and_check_cb(qtbot, mock_handler_gui.interface_dd, MOCK_INTERFACE)
        set_and_check_cb(qtbot, mock_handler_gui.module_dd, module_info.label)
        qtbot.mouseClick(mock_handler_gui.buttons["service_help"], LB)
        resp = mock_handler_gui.under_test_help_button_response
        assert resp and resp.ok
        qtbot.wait(100)


def test_help_button_not_clickable(qtbot, gui):
    for module_info in MODULE_INFOS:
        if module_info.docs_url:
            continue
        set_and_check_cb(qtbot, gui.interface_dd, MOCK_INTERFACE)
        set_and_check_cb(qtbot, gui.module_dd, module_info.label)
        assert not gui.buttons["service_help"].isEnabled()
        qtbot.wait(100)


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
