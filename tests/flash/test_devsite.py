# Copyright (c) Acconeer AB, 2025-2026
# All rights reserved
"""
pytest is configured to skip these test unless '--test-devsite'
is given on the CLI.

Run only the tests in this file with hatch with the command
$ hatch test tests/flash/test_devsite.py --test-devsite
"""

import os
import typing as t

import bs4
import pytest

from acconeer.exptool._artifact_repository import Artifact, DevSiteRepository, LoginRequiredError
from acconeer.exptool._dev_license import DevLicense


# Marks all tests in this file as "devsite"
pytestmark = pytest.mark.devsite


@pytest.fixture
def valid_credentials(is_running_in_ci: bool) -> tuple[str, str]:
    username = os.getenv("DEV_USERNAME")
    password = os.getenv("DEV_PASSWORD")

    if username is None or password is None:
        if is_running_in_ci:
            reason = "DEV_USERNAME & DEV_PASSWORD needs to be specified when running in Jenkins."
            pytest.fail(reason=reason)
        else:
            reason = "Incomplete credentials in env.vars. DEV_USERNAME & DEV_PASSWORD."
            pytest.skip(reason=reason)

    return (username, password)


def test_login_succeeds_with_valid_credentials(valid_credentials: tuple[str, str]) -> None:
    (username, password) = valid_credentials
    repo = DevSiteRepository(cookies=None)
    repo.login(username, password)
    assert repo.has_logged_in_previously()


def test_login_fails_with_invalid_credentials() -> None:
    repo = DevSiteRepository(cookies=None)
    repo.login("example@acconeer.com", "this_is_not_a_real_password")
    assert not repo.has_logged_in_previously()


def test_download_raises_login_required_without_a_valid_session() -> None:
    repo = DevSiteRepository(cookies=None)
    with pytest.raises(LoginRequiredError):
        repo.download(Artifact.XC120_EXPLORATION_SERVER, path=".")


def test_cookiejar_contains_logged_in_cookie(
    valid_credentials: tuple[str, str],
) -> None:
    (username, password) = valid_credentials
    repo = DevSiteRepository(cookies=None)
    repo.login(username, password)
    assert repo.cookies is not None

    found = False
    for k, v in repo.cookies.items():
        if "logged_in" in k:
            found = True

    assert found, "No cookie with name '*_logged_in_*' was found in cookiejar."


def test_logged_in_cookie_value_start_with_mangled_username(
    valid_credentials: tuple[str, str],
) -> None:
    (username, password) = valid_credentials
    repo = DevSiteRepository(cookies=None)
    repo.login(username, password)
    assert repo.cookies is not None

    for k, v in repo.cookies.items():
        if "logged_in" in k:
            mangled_username = username.replace(".", "-").replace("@", "")
            assert v.startswith(mangled_username + "%")
            break
    else:
        assert False, "No cookie with name '*_logged_in_*' was found in cookiejar."


def test_license_subheader_element_is_not_the_literal_string_none() -> None:
    license = DevLicense()
    license.load()
    assert license.html is not None, "Could not fetch the license page from production."

    subheader_element = license.get_subheader_element()
    assert subheader_element != "None", (
        "get_subheader_element() returned the literal string 'None' instead of "
        "falling back to a default: production page has no <h3> tag for it to find."
    )


def test_license_content_elements_contains_the_full_agreement_text() -> None:
    """The live page is ~70 lines, ~3k words and ~22KB: large enough that
    accidentally filtering out every paragraph (as opposed to truly having
    no content) is easy to tell apart from a short fallback message.
    """
    license = DevLicense()
    license.load()
    assert license.html is not None, "Could not fetch the license page from production."

    content = "".join(license.get_content_elements())
    assert len(content) > 15_000, (
        "get_content_elements() returned far less than the ~22KB agreement text, "
        "meaning most or all of its paragraphs were filtered out of the result."
    )


def _is_heading(tag: bs4.Tag) -> bool:
    if tag.name in ("h2", "h3", "h4"):
        return True
    if tag.name != "p":
        return False
    # A <p> that's otherwise just one <strong> run (plus a stray "&nbsp;",
    # as the real page has) is how it marks section 9 onwards, with no
    # heading tag at all.
    non_blank_children = [
        child
        for child in tag.contents
        if not (isinstance(child, bs4.NavigableString) and not child.strip())
    ]
    return (
        len(non_blank_children) == 1
        and isinstance(non_blank_children[0], bs4.Tag)
        and non_blank_children[0].name == "strong"
    )


def _group_by_heading(elements: t.Sequence[str]) -> list[tuple[str, list[str]]]:
    """Buckets a flat element list into (heading, body) sections.

    Elements before the first heading are dropped: nothing in the license is
    meant to be read without a section heading above it.
    """
    sections: list[tuple[str, list[str]]] = []
    for element in elements:
        tag = bs4.BeautifulSoup(element, "html.parser").find()
        if tag is None:
            continue
        assert isinstance(tag, bs4.Tag)
        if _is_heading(tag):
            sections.append((tag.get_text(strip=True), []))
        elif sections:
            sections[-1][1].append(tag.get_text(strip=True))
    return sections


def test_license_content_elements_has_one_section_per_heading() -> None:
    """The agreement has 11 numbered sections, the last being "11.
    APPLICABLE LAW", plus its "IMPORTANT-READ CAREFULLY:" preamble and its
    subheader: 13 headings in total, each owning at least its own text.
    """
    license = DevLicense()
    license.load()
    assert license.html is not None, "Could not fetch the license page from production."

    sections = _group_by_heading(license.get_content_elements())
    assert len(sections) == 13, (
        "Expected 13 sections (subheader, preamble and 11 numbered articles); "
        "got a different count, meaning either a heading was dropped or "
        "developer.acconeer.com's page structure changed."
    )
    assert all(heading for heading, _paragraphs in sections)
