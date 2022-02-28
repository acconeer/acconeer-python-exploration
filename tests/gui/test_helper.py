from unittest.mock import Mock

import pytest

from acconeer.exptool.app.elements import helper


@pytest.fixture
def calibration_ui_state() -> helper.CalibrationUiState:
    auto_apply_cb_mock = Mock()
    return helper.CalibrationUiState(auto_apply_cb=auto_apply_cb_mock)


def test_fields_with_newly_instantiated_ui_state(calibration_ui_state):
    assert calibration_ui_state.get_display_text() == ""
    assert not calibration_ui_state.is_display_text_italic
    assert not calibration_ui_state.save_button_enabled
    assert calibration_ui_state.load_button_enabled
    assert not calibration_ui_state.clear_button_enabled
    assert not calibration_ui_state.auto_apply
    assert not calibration_ui_state.apply_button_enabled


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("/home/test/Documents/test.yaml", ".../test.yaml"),
        ("~/test/Documents/test.yaml", ".../test.yaml"),
        ("./test.yaml", "test.yaml"),
    ],
)
def test_display_text_for_file_names(calibration_ui_state, filename, expected):
    calibration_ui_state.source = filename
    assert calibration_ui_state.get_display_text() == expected
    calibration_ui_state.modified = True
    assert calibration_ui_state.get_display_text() == expected + "*"


def test_display_italic(calibration_ui_state):
    assert not calibration_ui_state.is_display_text_italic
    calibration_ui_state.modified = True
    assert calibration_ui_state.is_display_text_italic


def test_display_text_for_session(calibration_ui_state):
    calibration_ui_state.source = "Session"
    assert calibration_ui_state.get_display_text() == "Session"
    calibration_ui_state.modified = True
    assert calibration_ui_state.get_display_text() == "Session*"


def test_save_button_state(calibration_ui_state):
    assert not calibration_ui_state.save_button_enabled
    calibration_ui_state.modified = True
    assert calibration_ui_state.save_button_enabled


def test_load_button_state(calibration_ui_state):
    assert calibration_ui_state.load_button_enabled
    calibration_ui_state.modified = True
    assert not calibration_ui_state.load_button_enabled


def test_apply_button_state(calibration_ui_state):
    assert not calibration_ui_state.apply_button_enabled
    calibration_ui_state.source = "smth"
    assert calibration_ui_state.apply_button_enabled


def test_clear_button_state(calibration_ui_state):
    assert not calibration_ui_state.clear_button_enabled
    calibration_ui_state.source = "Session"
    assert calibration_ui_state.clear_button_enabled


@pytest.mark.parametrize("is_modified", [True, False])
def test_correct_state_after_clear_is_pressed(calibration_ui_state, is_modified):
    calibration_ui_state.source = "a_filename"
    calibration_ui_state.modified = is_modified
    calibration_ui_state.clear()
    assert not calibration_ui_state.save_button_enabled
    assert not calibration_ui_state.clear_button_enabled
    assert calibration_ui_state.load_button_enabled
    assert calibration_ui_state.get_display_text() == ""


def test_save_verb(calibration_ui_state):
    calibration_ui_state.save("test")
    assert calibration_ui_state.source == "test"
    assert not calibration_ui_state.modified


def test_load_verb(calibration_ui_state):
    calibration_ui_state.load("test")
    assert calibration_ui_state.source == "test"
    assert not calibration_ui_state.modified


def test_autoapply_checkbox(calibration_ui_state):
    calibration_ui_state.auto_apply = True
    assert calibration_ui_state.auto_apply
    calibration_ui_state._auto_apply_cb.setChecked.assert_called_with(True)
