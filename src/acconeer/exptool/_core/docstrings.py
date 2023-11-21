# Copyright (c) Acconeer AB, 2023
# All rights reserved
from __future__ import annotations

import typing as t

import attributes_doc


def get_docstring(obj: t.Any) -> t.Optional[str]:
    """Gets the docstring of an object"""
    return getattr(obj, "__doc__", None)


def get_attribute_docstring(obj: t.Any, attribute_name: str) -> t.Optional[str]:
    """
    Given an object, retrieve the docstring for the attribute_name with name
    `attribute_name`.

    `attributes_doc` decorated classes are supported
    (see https://pypi.org/project/attributes-doc/)
    """
    return _get_attribute_docstring_vanilla(obj, attribute_name) or attributes_doc.get_doc(
        obj, attribute_name
    )


def _get_attribute_docstring_vanilla(obj: t.Any, attribute_name: str) -> t.Optional[str]:
    attribute = getattr(obj, attribute_name, None)
    if attribute is None:
        return None
    else:
        return get_docstring(attribute)
