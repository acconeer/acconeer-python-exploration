# Copyright (c) Acconeer AB, 2023
# All rights reserved

import attrs
from attributes_doc import attributes_doc

from acconeer.exptool._core.docstrings import get_attribute_docstring, get_docstring


@attributes_doc
class Positive:
    class_member: int
    """class_member doc"""

    @property
    def prop(self) -> int:
        """prop doc"""
        return 1


class Negative:
    class_member: int
    """class_member doc"""

    @property
    def prop(self) -> int:
        return 1


@attributes_doc
@attrs.mutable
class PosAttrs:
    field: int
    """field doc"""

    @property
    def prop(self) -> int:
        """prop doc"""
        return 1


@attrs.mutable
class NegAttrs:
    field: int
    """field doc"""

    @property
    def prop(self) -> int:
        return 1


def test_access_docstrings() -> None:
    assert get_attribute_docstring(Positive, "class_member") == "class_member doc"
    assert get_attribute_docstring(Positive, "prop") == get_docstring(Positive.prop) == "prop doc"

    assert get_attribute_docstring(Negative, "class_member") is None
    assert get_attribute_docstring(Negative, "prop") is get_docstring(Negative.prop) is None

    assert get_attribute_docstring(PosAttrs, "field") == "field doc"
    assert get_attribute_docstring(PosAttrs, "prop") == get_docstring(PosAttrs.prop) == "prop doc"

    assert get_attribute_docstring(NegAttrs, "field") is None
    assert get_attribute_docstring(NegAttrs, "prop") is get_docstring(NegAttrs.prop) is None
