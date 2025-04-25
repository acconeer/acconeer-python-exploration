# Copyright (c) Acconeer AB, 2023-2025
# All rights reserved
from __future__ import annotations

import typing as t
from enum import Enum

import attrs
import h5py
import numpy as np

from . import core
from .builtin_persistors import ListPersistor
from .registry_persistor import RegistryPersistor


@RegistryPersistor.register_persistor
class ScalarListPersistor(core.Persistor):
    """
    Persists lists of scalar types as a single Dataset
    """

    PRIORITY: t.ClassVar[int] = RegistryPersistor.priority_higher_than(ListPersistor)

    SCALARS = (float, int, bool)

    @classmethod
    def is_applicable(cls, __type: core.TypeLike) -> bool:
        should_be_list, *type_args = core.unwrap_generic(__type)

        if should_be_list is list:
            (type_arg,) = type_args
            return core.is_subclass(type_arg, cls.SCALARS)
        else:
            return False

    def _save(self, data: t.Any) -> None:
        if not isinstance(data, list):
            raise core.TypeMissmatchError

        (element_type_tree,) = self.type_tree.children.values()

        if any(not isinstance(e, element_type_tree.data) for e in data):
            raise core.TypeMissmatchError

        self.create_own_dataset(data)

    def _load(self) -> t.Any:
        dataset_contents = self.dataset[()]

        self.assert_not_empty(dataset_contents)

        (element_type_tree,) = self.type_tree.children.values()
        element_type = element_type_tree.data

        if not core.is_subclass(element_type, self.SCALARS):
            raise RuntimeError

        return [element_type(e) for e in dataset_contents]


@RegistryPersistor.register_persistor
class RaggedNumpyArrayPersistor(core.Persistor):
    """
    Persists "ragged" (and maybe optional) numpy arrays (list of numpy arrays)
    """

    PRIORITY: t.ClassVar[int] = RegistryPersistor.priority_higher_than(ListPersistor)

    @classmethod
    def is_applicable(cls, __type: core.TypeLike) -> bool:
        should_be_list, *type_args = core.unwrap_generic(__type)

        if should_be_list is not list:
            return False

        (type_arg,) = type_args

        if core.is_ndarray(type_arg):
            return True

        return core.is_optional(type_arg) and core.is_ndarray(core.optional_arg(type_arg))

    def _save(self, data: t.Any) -> None:
        if not isinstance(data, list):
            raise core.TypeMissmatchError

        if max(np.ndim(array) for array in data) > 1:
            msg = "Only 1-dimensional arrays can be ragged."
            raise core.SaveError(msg)

        try:
            (dtype,) = {arr.dtype for arr in data if arr is not None}
        except ValueError as ve:
            raise core.TypeMissmatchError from ve

        ragged_dtype = h5py.vlen_dtype(dtype)
        num_arrays = len(data)

        ragged_dataset = self.create_own_dataset(
            data=None,
            shape=(num_arrays,),
            dtype=ragged_dtype,
        )

        for i, array in enumerate(data):
            ragged_dataset[i] = array

    def _load(self) -> t.List[t.Any]:
        self.assert_not_empty(self.dataset[()])

        return list(self.dataset[()])


@RegistryPersistor.register_persistor
class TrileanListPersistor(core.Persistor):
    """
    Persists lists of "trileans" (i.e. Optional[bool]) by encoding it as an enum.
    """

    PRIORITY: t.ClassVar[int] = RegistryPersistor.priority_higher_than(ListPersistor)

    @classmethod
    def is_applicable(cls, __type: core.TypeLike) -> bool:
        should_be_list, *type_args = core.unwrap_generic(__type)

        if should_be_list is list:
            (type_arg,) = type_args
            return type_arg == t.Optional[bool]
        else:
            return False

    def _save(self, data: t.Any) -> None:
        if not isinstance(data, list):
            raise core.TypeMissmatchError

        if any(e not in {True, False, None} for e in data):
            raise core.TypeMissmatchError

        self.create_own_dataset(
            data=[_Trilean.from_object_value(e).stored_value for e in data],
            dtype=_Trilean.dtype(),
        )

    def _load(self) -> t.List[t.Optional[bool]]:
        self.assert_not_empty(self.dataset[()])

        return [_Trilean.from_stored_value(e).object_value for e in self.dataset[()]]


class _Trilean(Enum):
    TRUE = (0, True)
    FALSE = (1, False)
    NONE = (2, None)

    @property
    def stored_value(self) -> int:
        return int(self.value[0])

    @property
    def object_value(self) -> t.Optional[bool]:
        return self.value[1]  # type: ignore[no-any-return]

    @classmethod
    def from_stored_value(cls, value: int) -> t.Any:
        return {member.stored_value: member for member in cls}.get(value)

    @classmethod
    def from_object_value(cls, value: t.Optional[bool]) -> t.Any:
        return {member.object_value: member for member in cls}.get(value)

    @classmethod
    def dtype(cls) -> h5py.Datatype:
        return h5py.enum_dtype(
            {member.name: member.stored_value for member in cls},
            basetype="u1",
        )


@RegistryPersistor.register_persistor
class OptionalFloatListPersistor(core.Persistor):
    """
    Persists a list of Optional[float] by encoding ``None``s as np.inf
    if no np.inf exists in the list
    """

    PRIORITY: t.ClassVar[int] = RegistryPersistor.priority_higher_than(ListPersistor)

    SENTINEL = np.inf

    @classmethod
    def is_applicable(cls, __type: core.TypeLike) -> bool:
        should_be_list, *type_args = core.unwrap_generic(__type)

        if should_be_list is list:
            (type_arg,) = type_args
            return type_arg == t.Optional[float]
        else:
            return False

    def _save(self, data: t.Any) -> None:
        if any(e == self.SENTINEL for e in data):
            raise core.TypeMissmatchError

        data_with_replaced_nones = [(self.SENTINEL if e is None else e) for e in data]

        self.create_own_dataset(data_with_replaced_nones)

    def _load(self) -> t.List[t.Optional[float]]:
        self.assert_not_empty(self.dataset[()])

        return [(None if e == self.SENTINEL else float(e)) for e in self.dataset[()]]


@RegistryPersistor.register_persistor
class OptionalIntListPersistor(core.Persistor):
    """
    Persists a list of Optional[int] by encoding ``None``s as
    ``np.iinfo(np.int64).min`` (minimum value of int64)
    if the minimum values doesn't exists in the list
    """

    PRIORITY: t.ClassVar[int] = RegistryPersistor.priority_higher_than(ListPersistor)

    SENTINEL = np.iinfo(np.int64).min

    @classmethod
    def is_applicable(cls, __type: core.TypeLike) -> bool:
        should_be_list, *type_args = core.unwrap_generic(__type)

        if should_be_list is list:
            (type_arg,) = type_args
            return type_arg == t.Optional[int]
        else:
            return False

    def _save(self, data: t.Any) -> None:
        if any(e == self.SENTINEL for e in data):
            raise core.TypeMissmatchError

        data_with_replaced_nones = [(self.SENTINEL if e is None else e) for e in data]

        self.create_own_dataset(data_with_replaced_nones)

    def _load(self) -> t.List[t.Optional[float]]:
        self.assert_not_empty(self.dataset[()])

        return [(None if e == self.SENTINEL else int(e)) for e in self.dataset[()]]


@RegistryPersistor.register_persistor
class EnumListPersistor(core.Persistor):
    """
    Persists a list of (maybe optional) enums by encoding them as integers in a single Dataset
    """

    PRIORITY: t.ClassVar[int] = RegistryPersistor.priority_higher_than(ListPersistor)

    @classmethod
    def is_applicable(cls, __type: core.TypeLike) -> bool:
        should_be_list, *type_args = core.unwrap_generic(__type)

        if should_be_list is not list:
            return False
        (type_arg,) = type_args

        if core.is_subclass(type_arg, Enum):
            return True

        return core.is_optional(type_arg) and core.is_subclass(core.optional_arg(type_arg), Enum)

    @property
    def enum_class(self) -> t.Type[Enum]:
        (element_type_tree,) = self.type_tree.children.values()
        element_type = element_type_tree.data

        if core.is_subclass(element_type, Enum):
            return element_type
        elif core.is_optional(element_type) and core.is_subclass(
            core.optional_arg(element_type), Enum
        ):
            return core.optional_arg(element_type)
        else:
            raise RuntimeError

    @property
    def is_optional(self) -> bool:
        (element_type_tree,) = self.type_tree.children.values()
        element_type = element_type_tree.data
        return core.is_optional(element_type)

    def _save(self, data: t.Any) -> None:
        if not isinstance(data, list):
            raise core.TypeMissmatchError

        h5_enum = H5Enum(self.enum_class, include_none=self.is_optional)

        self.create_own_dataset(
            data=[h5_enum.stored_value(e) for e in data],
            dtype=h5_enum.dtype(),
        )

    def _load(self) -> t.List[t.Optional[Enum]]:
        self.assert_not_empty(self.dataset[()])

        h5_enum = H5Enum(self.enum_class, include_none=self.is_optional)

        return [h5_enum.member(e) for e in self.dataset[()]]


@attrs.frozen
class H5Enum:
    enum_class: t.Type[Enum] = attrs.field(validator=attrs.validators.max_len(2**8 - 2))
    include_none: bool = attrs.field(default=False)

    NONE_NAME: t.ClassVar[str] = "NONE"

    @property
    def _name_mapping(self) -> dict[str, int]:
        return {
            **{member.name: index for index, member in enumerate(self.enum_class)},
            **({self.NONE_NAME: len(self.enum_class)} if self.include_none else {}),
        }

    @property
    def _stored_mapping(self) -> dict[int, str]:
        return {index: name for name, index in self._name_mapping.items()}

    def stored_value(self, member: t.Optional[Enum]) -> int:
        return self._name_mapping[self.NONE_NAME if member is None else member.name]

    def member(self, stored_value: int) -> t.Optional[Enum]:
        name = self._stored_mapping[stored_value]
        if name == self.NONE_NAME:
            return None
        else:
            return self.enum_class[self._stored_mapping[stored_value]]

    def dtype(self) -> h5py.Datatype:
        return h5py.enum_dtype(self._name_mapping, basetype="u1")


@RegistryPersistor.register_persistor
class SausageableAttrsPersistor(core.Persistor):
    """
    Sausages attrs classes that are in a list.

    e.g. the list of attrs instances below

    .. codeblock: python
        @attrs.define
        class Foo:
            i: int
            f: float

        [Foo(1, 1.0), Foo(2, 2.0), Foo(3, 3.0), ...]

    is persisted as if ``Foo`` was defined like

    .. codeblock: python
        @attrs.define
        class Foo:
            i: t.List[int]
            f: t.List[float]

        Foo([1, 2, 3, ...], [1.0, 2.0, 3.0, ...])

    which can allow the fields ``i`` and ``f`` to be saved more efficiently.
    """

    PRIORITY: t.ClassVar[int] = RegistryPersistor.priority_higher_than(ListPersistor)

    @classmethod
    def is_applicable(cls, __type: core.TypeLike) -> bool:
        if not core.is_generic(__type):
            return False

        origin, *type_args = core.unwrap_generic(__type)

        if origin is not list:
            return False

        (type_arg,) = type_args
        return attrs.has(type_arg)

    def _save(self, data: t.Any) -> None:
        (attrs_type_tree,) = self.type_tree.children.values()

        if not isinstance(data, list):
            raise core.TypeMissmatchError

        for attribute_name, attribute_type_tree in attrs_type_tree.children.items():
            RegistryPersistor(
                self.require_own_group(),
                attribute_name,
                core.Node(
                    t.List[attribute_type_tree.data],  # type: ignore[name-defined]
                    {attribute_name: attribute_type_tree},
                ),
            ).save([getattr(attrs_instance, attribute_name) for attrs_instance in data])

    def _load(self) -> t.List[attrs.AttrsInstance]:
        (attrs_type_tree,) = self.type_tree.children.values()
        attrs_type = attrs_type_tree.data

        assert attrs.has(attrs_type)

        attribute_lists = {
            attribute_name: RegistryPersistor(
                self.group,
                attribute_name,
                core.Node(
                    t.List[attribute_type_tree.data],  # type: ignore[name-defined]
                    {attribute_name: attribute_type_tree},
                ),
            ).load()
            for attribute_name, attribute_type_tree in attrs_type_tree.children.items()
        }

        lengths = {
            len(attribute_list) for attribute_name, attribute_list in attribute_lists.items()
        }

        (length,) = lengths

        list_of_kwargs = [
            {
                attribute_name.strip("_"): attribute_list[index]
                for attribute_name, attribute_list in attribute_lists.items()
            }
            for index in range(length)
        ]

        return [attrs_type(**kwargs) for kwargs in list_of_kwargs]
