# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved

from __future__ import annotations

import contextlib
import typing as t

import typing_extensions as te

from acconeer.exptool._core.docstrings import get_attribute_docstring, get_docstring


_T = t.TypeVar("_T")


@te.runtime_checkable
class Descriptor(te.Protocol[_T]):
    def __get__(self, obj: t.Any, objtype: t.Optional[type] = None) -> _T: ...

    def __set__(self, obj: t.Any, value: _T) -> None: ...


def delegate_field(
    delegate_name: str,
    descriptor: t.Any,
    type_: type[_T],
    *,
    doc: t.Union[str, type, None] = None,
    error_format: t.Optional[str] = None,
) -> Descriptor[_T]:
    """
    Generate a property of the outer class that modifies an inner class's fields.

    Example:

    >>> import attrs
    >>>
    >>> @attrs.mutable
    ... class Wheel:
    ...     rpm: float
    ...     angle: float
    >>>
    >>> @attrs.mutable
    ... class Bike:
    ...     front_wheel: Wheel
    ...     back_wheel: Wheel
    ...
    ...     # Note the missing type annotations here
    ...     rpm = delegate_field("back_wheel", Wheel.rpm, type_=float, doc="Rpm of the back wheel")
    ...     angle = delegate_field("front_wheel", Wheel.angle, type_=float, doc="Angle of the front wheel")
    >>>
    >>> b = Bike(Wheel(0, 0), Wheel(0, 0))
    >>> b.rpm = 70
    >>> b.angle = 45
    >>> b
    Bike(front_wheel=Wheel(rpm=0, angle=45), back_wheel=Wheel(rpm=70, angle=0))

    >>> Bike.rpm.__doc__
    'Rpm of the back wheel'
    >>> Bike.angle.__doc__
    'Angle of the front wheel'

    :param delegate_name:
            Name of the the attribute that holds an object to delegate to
    :param descriptor:
            The descriptor to delegate to.
            Works for "attrs.field"s and "property"s
    :param type_:
            The type of the resulting property.
    :param doc:
            If str:             This will be the property's docstring. An empty
                                string will set __doc__ = None.
            If a class (type):  Will attempt to find a docstring in the class,
                                using the descriptor name.
                                If no docstring can be found, an error will be raised.
            If omitted or None: Uses descriptor.__doc__ unless
                                it's None (which will result in an error)
    :param error_format:
            Used to change the AttributeError's message.
            The catched AttributeError originates from ~`getattr(self, delegate_name)`.
            It's format string that accepts the keywords
            'descriptor_name' and 'delegate_name', e.g.

                "descriptor is {descriptor_name} & delegate is {delegate_name}"

    :returns:
            A delegating property
    """
    if not isinstance(descriptor, Descriptor):
        msg = f"Passed object {descriptor} is not a descriptor"
        raise TypeError(msg)

    def getter(obj: t.Any) -> _T:
        with _more_helpful_attribute_error(error_format, delegate_name, descriptor):
            delegate = getattr(obj, delegate_name)

        return descriptor.__get__(delegate)  # type: ignore[no-any-return]

    def setter(obj: t.Any, value: _T) -> None:
        with _more_helpful_attribute_error(error_format, delegate_name, descriptor):
            delegate = getattr(obj, delegate_name)

        descriptor.__set__(delegate, value)

    return property(
        fget=_with_return_type_annotation(getter, type_),
        fset=setter,
        doc=_determine_docstring(doc, descriptor),
    )


def _descriptor_given_name(descriptor: t.Any) -> t.Optional[str]:
    if isinstance(descriptor, property):
        return getattr(descriptor.fget, "__name__", None)

    return getattr(descriptor, "__name__", None)


@contextlib.contextmanager
def _more_helpful_attribute_error(
    error_format: t.Optional[str],
    delegate_name: str,
    descriptor: t.Any,
) -> t.Iterator[None]:
    try:
        yield
    except AttributeError as e:
        if error_format is None:
            raise e

        raise AttributeError(
            error_format.format(
                descriptor_name=_descriptor_given_name(descriptor),
                delegate_name=delegate_name,
            )
        ) from None


def _with_return_type_annotation(
    f: t.Callable[..., _T], return_type: type[_T]
) -> t.Callable[..., _T]:
    """
    This function patches a function's return type annotation.
    If used on the getter of a property, Sphinx seems to collect
    that type as the property return type
    """
    f.__annotations__["return"] = return_type.__name__
    return f


def _determine_docstring(
    doc: t.Union[str, type, None], descriptor: Descriptor[t.Any]
) -> t.Optional[str]:
    """See behaviour of "doc" parameter in delegate_field."""
    if isinstance(doc, str):
        return None if doc == "" else doc
    elif doc is None and get_docstring(descriptor) is not None:
        return get_docstring(descriptor)
    elif isinstance(doc, type):
        descriptor_name = _descriptor_given_name(descriptor)
        if descriptor_name is not None:
            docstring = get_attribute_docstring(doc, descriptor_name)
            if docstring is not None:
                return docstring

    raise RuntimeError(
        f"Could not automatically find docstring for {descriptor}. "
        + 'Specify docs manually (doc="...") or skip it (doc="")'
    )
