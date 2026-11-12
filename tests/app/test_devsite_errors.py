# Copyright (c) Acconeer AB, 2026
# All rights reserved
from __future__ import annotations

from acconeer.exptool._artifact_repository import ArtifactRepositoryError
from acconeer.exptool.app.new.ui.components.devsite import get_internet_related_error_message


def test_unexpected_error_with_non_string_args_is_described() -> None:
    message = get_internet_related_error_message(RuntimeError(404, "Not Found"))

    assert "404" in message
    assert "Not Found" in message


def test_unexpected_error_without_args_is_named() -> None:
    message = get_internet_related_error_message(TimeoutError())

    assert "TimeoutError" in message


def test_unexpected_error_advises_what_to_try_next() -> None:
    message = get_internet_related_error_message(RuntimeError(404, "Not Found"))

    assert "report it to Acconeer support" in message


def test_unexpected_error_advice_precedes_details() -> None:
    message = get_internet_related_error_message(RuntimeError(404, "Not Found"))

    assert message.index("Acconeer support") < message.index("404")


def test_artifact_repository_error_is_shown_as_its_own_advice() -> None:
    advice = "This ET release expects algo bundle version 8.0.0, but the site offers 9.0.0."

    message = get_internet_related_error_message(ArtifactRepositoryError(advice))

    assert message == advice
