from __future__ import annotations

from typing import Any, Callable, Generic, Optional, TypeVar, Union


T = TypeVar("T")

KeyT = TypeVar("KeyT")
ValueT = TypeVar("ValueT")


class ProxyProperty(Generic[T]):
    """
    A descriptor that reduces boilerplate for accessing a certain property in a component.
    If the proxied property has a doc-string, it will be inherited by this descriptor.

    E.g. This can be used to implement "first-element-shortcuts"


        class Component:
            _attribute: int

            ...

            @property
            def attribute(self) -> int:
                return self._attribute

            @attribute.setter
            def attribute(self, new_value: int):
                self._attribute = new_value

        class Container:
            proxy_attribute = ProxyProperty[Component, int](
                lambda container: container.get_first_component(), Component.attribute
            )

            def get_first_component(self):
                ...

    It's recommended to subclass ProxyProperty to fit each Component-Container combination.
    """

    def __init__(
        self,
        accessor: Callable,
        prop: property,
    ):
        """
        :param accessor: The function to call to recieve an object that has the property "prop".
        :param prop: The property object which to proxy upon.
        """
        self._accessor = accessor
        if not isinstance(prop, property):
            raise TypeError(f'Passed "prop" needs to be a property. Actual type: {type(prop)}')
        self._property = prop

        self.__doc__ = prop.__doc__

    def __get__(
        self,
        obj: Any,
        objtype: Any = None,
    ) -> Union[T, ProxyProperty[T]]:
        if obj is not None:
            proxee = self._accessor(obj)
            # The reason this needs to be ignored boils down to lack of support for
            # generic descriptors (property is a descriptor) in mypy.
            return self._property.__get__(proxee)  # type: ignore[no-any-return]

        return self

    def __set__(self, obj: Any, value: T) -> None:
        proxee = self._accessor(obj)
        self._property.__set__(proxee, value)


def convert_validate_int(
    value: Union[float, int], max_value: Optional[int] = None, min_value: Optional[int] = None
) -> int:
    """Converts an argument to an int.

    :param value: The argument to be converted and boundary checked
    :param max_value: Maximum value allowed
    :param min_value: Minimum value allowed

    :raises: TypeError if value is a string or a float with decimals
    :raises: ValueError if value does not agree with max_value and min_value
    """
    try:
        int_value = int(value)  # may raise ValueError if "value" is a non-int string
        if int_value != value:  # catches e.g. int("3") != "3", int(3.5) != 3.5.
            raise ValueError
    except ValueError:
        raise TypeError(f"{value} cannot be fully represented as an int.")

    if max_value is not None and int_value > max_value:
        raise ValueError(f"Cannot be greater than {max_value}")

    if min_value is not None and int_value < min_value:
        raise ValueError(f"Cannot be less than {min_value}")

    return int_value


def is_multiple_of(multiplier: int, product: int) -> bool:
    """Returns True if `product` is a multiple of `multiplier`.
    I.e. checks if `multiplicand` is an integer in the equation

    `multiplicand` * `multiplier` = `product`
    """
    return product >= multiplier and product % multiplier == 0


def is_divisor_of(divisor: int, dividend: int) -> bool:
    """Returns True if `dividend` is divided by `divisor` with no remainder
    I.e. checks that `quotient` is an integer in the equation

    `dividend` / `divisor` = `quotient`
    """
    return is_multiple_of(dividend, divisor)


def map_over_extended_structure(
    func: Callable[[ValueT], T], structure: list[dict[KeyT, ValueT]]
) -> list[dict[KeyT, T]]:
    """Applies a function, `func`, to each element of the extended structure.

    Example:

        structure = [{1: "one"}, {2: "two"}]        # KeyT = int, ValueT = str
        func = str.encode                           # ValueT = str, T = bytes

        # Result
        result = [{1: b"one"}, {2: b"two"}]         # KeyT = int, T = bytes

    """
    return [{k: func(v) for k, v in d.items()} for d in structure]
