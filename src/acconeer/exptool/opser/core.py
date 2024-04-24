# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved

from __future__ import annotations

import abc
import json
import typing as t

import attrs
import exceptiongroup as eg
import h5py
import typing_extensions as te

from . import core


_T = t.TypeVar("_T")
TypeLike = t.Union[
    type,
    t._GenericAlias,  # type: ignore[name-defined]
]


class LoadError(Exception):
    def __repr__(self) -> str:
        return str(self)


class SaveError(Exception):
    def __repr__(self) -> str:
        return str(self)


class SaveErrorGroup(SaveError, eg.ExceptionGroup[Exception]):
    pass


class LoadErrorGroup(LoadError, eg.ExceptionGroup[Exception]):
    pass


class MissingH5ObjectError(LoadError):
    @classmethod
    def create(cls, parent: h5py.Group, name: str) -> te.Self:
        return cls(
            f"Expected group {parent} to contain child {name!r}, "
            + f"but it only contains {list(parent.keys())}"
        )


class WrongH5ObjectError(LoadError):
    def __init__(
        self,
        parent: h5py.Group,
        child: t.Union[h5py.Dataset, h5py.Group],
        expected_type: type,
    ) -> None:
        super().__init__(f"Member {child} of {parent} was expected to be a {expected_type}")


class TypeMissmatchError(SaveError):
    @classmethod
    def wrong_type_encountered(cls, instance: t.Any, *expected_types: type) -> te.Self:
        if expected_types == ():
            raise ValueError("Gotta specify at least one expected type")

        if len(expected_types) == 1:
            (expected_type,) = expected_types
            return cls(
                f"Expected type was {expected_type}. Encountered {instance} of type {type(instance)}"
            )
        else:
            return cls(
                f"Expected type was any of {expected_types}. Encountered {instance} of type {type(instance)}"
            )


class JsonPresentable(te.Protocol):
    def to_json(self) -> str:
        ...

    @classmethod
    def from_json(cls, json_string: str) -> te.Self:
        ...


@attrs.frozen
class Persistor(abc.ABC):
    PRIORITY: t.ClassVar[int] = 0

    parent_group: h5py.Group
    name: str
    type_tree: core.Node

    @classmethod
    def from_json_presentable(cls, presentable_type: t.Type[JsonPresentable]) -> t.Type[Persistor]:
        """Generates a Persistor class for the specified JsonPresentable"""

        def _is_applicable(cls: t.Type[Persistor], __type: core.TypeLike) -> bool:
            return core.is_subclass(__type, presentable_type)

        def _save(self: Persistor, data: t.Any) -> None:
            if not isinstance(data, presentable_type):
                raise TypeMissmatchError(data, self.type_tree, presentable_type)

            self.create_own_dataset(data=data.to_json())

        def _load(self: Persistor) -> JsonPresentable:
            dataset_contents = self.dataset[()]
            cls.assert_not_empty(dataset_contents)
            try:
                return presentable_type.from_json(bytes.decode(dataset_contents))
            except json.JSONDecodeError:
                raise LoadError

        return type(
            f"GeneratedPersistor_JsonPresentable_{presentable_type.__name__}",
            (Persistor,),
            {
                "is_applicable": classmethod(_is_applicable),
                "save": _save,
                "load": _load,
            },
        )

    @staticmethod
    def assert_not_empty(dataset_contents: t.Any) -> None:
        """Asserts that the dataset contents is not empty"""
        if isinstance(dataset_contents, h5py.Empty):
            raise core.LoadError

    @staticmethod
    def assert_empty(dataset_contents: t.Any) -> None:
        """Asserts that the dataset contents is not empty"""
        if not isinstance(dataset_contents, h5py.Empty):
            raise core.LoadError

    @property
    def group(self) -> h5py.Group:
        obj = self.parent_group.get(self.name, default=None)

        if isinstance(obj, h5py.Group):
            return obj
        elif obj is None:
            raise MissingH5ObjectError.create(self.parent_group, self.name)
        else:
            raise WrongH5ObjectError(self.parent_group, obj, expected_type=h5py.Group)

    @property
    def dataset(self) -> h5py.Dataset:
        obj = self.parent_group.get(self.name, default=None)

        if isinstance(obj, h5py.Dataset):
            return self.parent_group[self.name]
        elif obj is None:
            raise MissingH5ObjectError.create(self.parent_group, self.name)
        else:
            raise WrongH5ObjectError(self.parent_group, obj, expected_type=h5py.Dataset)

    def require_own_group(self) -> h5py.Group:
        group = self.parent_group.require_group(self.name)
        group.attrs["persistor"] = f"{type(self).__name__}"
        return group

    def create_own_dataset(self, data: t.Any, *, dtype: t.Any = None) -> h5py.Dataset:
        dataset = self.parent_group.create_dataset(self.name, data=data, dtype=dtype)
        dataset.attrs["persistor"] = f"{type(self).__name__}"
        return dataset

    @classmethod
    @abc.abstractmethod
    def is_applicable(cls, __type: core.TypeLike) -> bool:
        pass

    @abc.abstractmethod
    def save(self, data: t.Any) -> None:
        pass

    @abc.abstractmethod
    def load(self) -> t.Any:
        pass


class Node:
    """Basic tree node implementation."""

    def __init__(self, __data: t.Any, **children: Node) -> None:
        self.data = __data
        self.children = children
        self.parent: t.Optional[Node] = None

        for child in self.children.values():
            child.parent = self

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Node):
            return self.data == other.data and self.children == other.children
        else:
            return False

    def __repr__(self) -> str:
        if self.children == {}:
            return f"Node({self.data!r})"
        else:
            children_kwargs = ", ".join(
                f"{name}={child!r}" for name, child in self.children.items()
            )
            return f"Node({self.data!r}, {children_kwargs})"


def is_class(__type: TypeLike) -> te.TypeGuard[type]:
    """Return True if '__type' is a class"""
    return not core.is_ndarray(__type) and isinstance(__type, type)


def is_subclass(__type: TypeLike, superclass: t.Union[type, t.Tuple[type, ...]]) -> bool:
    """Return True if '__type' is a subclass of superclass"""
    return is_class(__type) and issubclass(__type, superclass)


def is_generic(__type: TypeLike) -> bool:
    """Return True if '__type' is a generic type"""
    return te.get_origin(__type) is not None and te.get_args(__type) != ()


def is_optional(__type: TypeLike) -> bool:
    """Return True if '__type' is an optional type"""
    origin, *type_args = unwrap_generic(__type)

    return origin is t.Union and type(None) in type_args and len(type_args) > 1


def optional_args(__type: TypeLike) -> t.Tuple[TypeLike, ...]:
    origin, *type_args = unwrap_generic(__type)

    return tuple(ta for ta in type_args if ta is not type(None))


def optional_arg(__type: TypeLike) -> TypeLike:
    (arg,) = optional_args(__type)
    return arg


def unwrap_generic(__type: TypeLike) -> t.Sequence[TypeLike]:
    """
    'Unwraps' a generic returning its origin and type args.

    For example:
        List[int] |-> (list, int)
        Dict[int, Enum] |-> (dict, int, Enum)
    """
    return (te.get_origin(__type), *te.get_args(__type))


def is_ndarray(__type: TypeLike) -> bool:
    # Extra check for numpy arrays (annotated with 'numpy.typing.NDArray').
    #   In versions <3.9/3.10, numpy has their own GenericAlias that does not play
    # well with the introspection functions from 'typing'.
    return getattr(__type, "__name__", None) == "ndarray"


def get_class_type_hints(__type: type) -> dict[str, TypeLike]:
    try:
        return t.get_type_hints(__type)
    except TypeError as error:
        raise TypeError(
            f"{__type} is annotated with built-ins (list, dict, etc.). "
            + "Use 'typing' counterpart instead (typing.List, typing.Dict, etc.)"
        ) from error


def sequence_index(index: t.Union[str, int] = "X") -> str:
    return f"sequence_index_{index}"


def union_index(index: int) -> str:
    return f"union_index_{index}"


DICT_KEY_TYPE = "dict_key_type"
DICT_VALUE_TYPE = "dict_value_type"


def create_type_tree(__type: TypeLike, parent: t.Optional[Node] = None) -> Node:
    if isinstance(__type, t.TypeVar):
        raise NotImplementedError("Cannot resolve type variables of generic classes")

    if is_class(__type):
        hints = get_class_type_hints(__type)
    elif is_ndarray(__type):
        hints = {}
    elif is_generic(__type):
        origin, *type_args = unwrap_generic(__type)

        if origin is list:
            (type_arg,) = type_args
            hints = {sequence_index(): type_arg}

        elif origin is dict:
            (key_type, value_type) = type_args
            hints = {
                DICT_KEY_TYPE: key_type,
                DICT_VALUE_TYPE: value_type,
            }

        elif origin is tuple:
            if ... in type_args:
                raise NotImplementedError("Tuple with ellipsis (...) is not supported")

            hints = {sequence_index(i): arg for i, arg in enumerate(type_args)}

        elif origin is t.Union:
            hints = {union_index(i): arg for i, arg in enumerate(type_args)}

        else:
            raise ValueError(
                f"Unexpected generic type '{__type}' (origin={origin}, type_args={type_args})"
            )
    else:
        raise RuntimeError(f"Unexpected type: '{__type}' of type {type(__type)}")

    try:
        return Node(
            __type,
            **{name: create_type_tree(hint) for name, hint in hints.items()},
        )
    except RecursionError:
        raise TypeError(f"{__type} is recursive. Recursively defined classes are not supported")


def sanitize_instance(instance: t.Any, type_tree: Node) -> None:
    """
    Asserts that the instance conforms to its type and type annotations with instance-checks
    """
    current_type = type_tree.data

    if is_ndarray(current_type):
        return
    elif is_class(current_type):
        if isinstance(instance, current_type):
            return
        else:
            raise TypeMissmatchError(instance, type_tree, current_type)
    elif is_generic(current_type):
        origin, *type_args = unwrap_generic(current_type)
        if origin is list:
            (child,) = type_tree.children.values()

            for value in instance:
                sanitize_instance(value, child)

            return

        elif origin is dict:
            (key_tree, value_tree) = type_tree.children.values()

            for key, value in instance.items():
                sanitize_instance(key, key_tree)
                sanitize_instance(value, value_tree)

            return

        elif origin is tuple:
            if ... in type_args:
                raise NotImplementedError("Tuple with ellipsis (...) is not supported")

            children = type_tree.children.values()

            assert len(children) == len(instance)
            for value, child in zip(instance, children):
                sanitize_instance(value, child)

            return

        elif origin is t.Union:
            children = type_tree.children.values()
            for child in children:
                try:
                    sanitize_instance(instance, child)
                except TypeMissmatchError:
                    continue
                else:
                    break
            else:
                raise TypeMissmatchError(instance, type_tree, *[c.data for c in children])

            return

        else:
            raise ValueError(
                f"Unexpected generic type '{current_type}' (origin={origin}, type_args={type_args})"
            )

        raise RuntimeError("Fell through instance sanitization")
