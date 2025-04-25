# Copyright (c) Acconeer AB, 2023-2025
# All rights reserved
from __future__ import annotations

import typing as t
from enum import Enum

import attrs
import numpy as np

from . import core
from .registry_persistor import RegistryPersistor


_T = t.TypeVar("_T")
_S = t.TypeVar("_S")


@RegistryPersistor.register_persistor
class StringPersistor(core.Persistor):
    """
    Persists a string by encoding/decoding to/from bytes
    """

    @classmethod
    def is_applicable(cls, __type: core.TypeLike) -> bool:
        return __type is str

    def _save(self, data: t.Any) -> None:
        if not isinstance(data, str):
            raise core.TypeMissmatchError.wrong_type_encountered(data, "?", str)

        self.create_own_dataset(data=data.encode())

    def _load(self) -> str:
        encoded_string = self.dataset[()]

        self.assert_not_empty(encoded_string)

        return bytes.decode(encoded_string)


@RegistryPersistor.register_persistor
class EnumPersistor(core.Persistor):
    """
    Persists an Enum value by saving/loading its encoded name to a dataset
    """

    @classmethod
    def is_applicable(cls, __type: core.TypeLike) -> bool:
        return core.is_subclass(__type, Enum)

    def _save(self, data: t.Any) -> None:
        if not isinstance(data, Enum):
            raise core.TypeMissmatchError.wrong_type_encountered(data, "?", Enum)

        self.create_own_dataset(data=data.name.encode())

    def _load(self) -> Enum:
        enum_name_in_bytes = self.dataset[()]

        self.assert_not_empty(enum_name_in_bytes)

        enum_type = self.type_tree.data

        return enum_type[bytes.decode(enum_name_in_bytes)]  # type: ignore[index, no-any-return]


@RegistryPersistor.register_persistor
class NonePersistor(core.Persistor):
    """
    Persists a None by saving/"loading" an empty dataset

    See: https://docs.h5py.org/en/stable/high/dataset.html#dataset-empty
    """

    @classmethod
    def is_applicable(cls, __type: core.TypeLike) -> bool:
        return core.is_subclass(__type, type(None))

    def _save(self, data: t.Any) -> None:
        if data is not None:
            raise core.TypeMissmatchError.wrong_type_encountered(data, "?", type(None))

        self.create_own_dataset(data, dtype="f")

    def _load(self) -> None:
        should_be_empty = self.dataset[()]

        self.assert_empty(should_be_empty)


@RegistryPersistor.register_persistor
class FloatPersistor(core.Persistor):
    """
    Persists floats.

    Also persists ints, but it is transformed to a float before saving
    """

    @classmethod
    def is_applicable(cls, __type: core.TypeLike) -> bool:
        return __type is float

    def _save(self, data: t.Any) -> None:
        if not isinstance(data, (float, int)):
            raise core.TypeMissmatchError.wrong_type_encountered(data, "?", float, int)

        if np.shape(data) != ():
            raise core.TypeMissmatchError

        self.create_own_dataset(data=float(data))

    def _load(self) -> float:
        should_be_float = self.dataset[()]

        self.assert_not_empty(should_be_float)

        return float(should_be_float)


@RegistryPersistor.register_persistor
class BoolPersistor(core.Persistor):
    """
    Persists bools
    """

    @classmethod
    def is_applicable(cls, __type: core.TypeLike) -> bool:
        return __type is bool

    def _save(self, data: t.Any) -> None:
        if data not in {True, False}:
            raise core.TypeMissmatchError.wrong_type_encountered(data, "?", bool, np.bool_)

        if np.shape(data) != ():
            raise core.TypeMissmatchError

        self.create_own_dataset(data=data)

    def _load(self) -> bool:
        should_be_bool = self.dataset[()]

        self.assert_not_empty(should_be_bool)

        return bool(should_be_bool)


@RegistryPersistor.register_persistor
class IntPersistor(core.Persistor):
    """
    Persists ints
    """

    @classmethod
    def is_applicable(cls, __type: core.TypeLike) -> bool:
        return __type is int

    def _save(self, data: t.Any) -> None:
        if not isinstance(data, (int, np.integer)):
            raise core.TypeMissmatchError.wrong_type_encountered(data, "?", int, np.integer)

        if np.shape(data) != ():
            raise core.TypeMissmatchError

        self.create_own_dataset(data=data)

    def _load(self) -> int:
        should_be_int = self.dataset[()]

        self.assert_not_empty(should_be_int)

        return int(should_be_int)


@RegistryPersistor.register_persistor
class ListPersistor(core.Persistor):
    """
    Persists lists of arbitrary type.

    Loading/saving recurses on each element in the list / member of the group
    """

    @classmethod
    def is_applicable(cls, __type: core.TypeLike) -> bool:
        should_be_list, *_ = core.unwrap_generic(__type)
        return should_be_list is list

    def _save(self, data: t.Any) -> None:
        if not isinstance(data, list):
            raise core.TypeMissmatchError.wrong_type_encountered(data, "?", list)

        (element_type_tree,) = self.type_tree.children.values()

        element_group = self.require_own_group()

        for i, element in enumerate(data):
            RegistryPersistor(element_group, str(i), element_type_tree).save(element)

    def _load(self) -> t.List[_T]:
        (element_type_tree,) = self.type_tree.children.values()

        return [
            RegistryPersistor(self.group, key, element_type_tree).load()
            for key in sorted(self.group.keys(), key=int)
        ]


@RegistryPersistor.register_persistor
class DictPersistor(core.Persistor):
    """
    Persists dicts

    dicts gets persisted as entries with key and value members. This allows
    both keys and values to be of arbitrary type
    """

    VALUE_GROUP_KEY = "val"
    KEY_GROUP_KEY = "key"

    @classmethod
    def is_applicable(cls, __type: core.TypeLike) -> bool:
        should_be_dict, *_ = core.unwrap_generic(__type)
        return should_be_dict is dict

    def _save(self, data: t.Any) -> None:
        if not isinstance(data, dict):
            raise core.TypeMissmatchError.wrong_type_encountered(data, "?", dict)

        (key_type_tree, value_type_tree) = self.type_tree.children.values()

        dict_group = self.require_own_group()

        for i, (key, value) in enumerate(data.items()):
            entry_group = dict_group.create_group(str(i))
            RegistryPersistor(entry_group, self.VALUE_GROUP_KEY, value_type_tree).save(value)
            RegistryPersistor(entry_group, self.KEY_GROUP_KEY, key_type_tree).save(key)

    def _load(self) -> t.Dict[_S, _T]:
        (key_type_tree, value_type_tree) = self.type_tree.children.values()

        return {
            RegistryPersistor(self.group[entry_index], self.KEY_GROUP_KEY, key_type_tree).load(): (
                RegistryPersistor(
                    self.group[entry_index], self.VALUE_GROUP_KEY, value_type_tree
                ).load()
            )
            for entry_index in sorted(self.group.keys(), key=int)
        }


@RegistryPersistor.register_persistor
class TuplePersistor(core.Persistor):
    """
    Persists non-variadic tuples with arbitrary types

    I.e. Tuple[str, int, SomeClass] is persisted like expected
    but Tulpe[int, ...] is not supported
    """

    @classmethod
    def is_applicable(cls, __type: core.TypeLike) -> bool:
        should_be_tuple, *_ = core.unwrap_generic(__type)
        return should_be_tuple is tuple

    def _save(self, data: t.Any) -> None:
        if not isinstance(data, tuple):
            raise core.TypeMissmatchError.wrong_type_encountered(data, "?", tuple)

        element_group = self.require_own_group()

        for i, (element_subtree, element) in enumerate(
            zip(self.type_tree.children.values(), data)
        ):
            RegistryPersistor(element_group, str(i), element_subtree).save(element)

    def _load(self) -> t.Tuple[t.Any, ...]:
        return tuple(
            RegistryPersistor(self.group, key, element_type_tree).load()
            for key, element_type_tree in zip(self.group.keys(), self.type_tree.children.values())
        )


@RegistryPersistor.register_persistor
class UnionPersistor(core.Persistor):
    """
    Persists union types

    Each member of the Union gets an attempt to persist before exiting
    """

    @classmethod
    def is_applicable(cls, __type: core.TypeLike) -> bool:
        should_be_union, *_ = core.unwrap_generic(__type)
        return should_be_union is t.Union

    def _save(self, data: t.Any) -> None:
        errors = []
        for member_type_tree in self.type_tree.children.values():
            try:
                RegistryPersistor(self.parent_group, self.name, member_type_tree).save(data)
            except core.SaveError as save_error:
                errors += [save_error]
                continue
            else:
                return

        msg = f"Could not save instance {data!r:.100}... of type {type(data)}"
        raise core.SaveErrorGroup(msg, errors)

    def _load(self) -> t.Any:
        errors = []
        for name, subtree in self.type_tree.children.items():
            try:
                res = RegistryPersistor(self.parent_group, self.name, subtree).load()
            except core.LoadError as load_error:
                errors += [load_error]
                continue
            else:
                return res

        child_types = tuple(st.data for st in self.type_tree.children.values())
        msg = f"Could not load any of {child_types} from {self.group}"
        raise core.LoadErrorGroup(msg, errors)


@RegistryPersistor.register_persistor
class AttrsInstancePersistor(core.Persistor):
    """
    Persists attrs instances
    """

    @classmethod
    def is_applicable(cls, __type: core.TypeLike) -> bool:
        return attrs.has(__type)

    def _save(self, data: t.Any) -> None:
        if not isinstance(data, self.type_tree.data):
            raise core.TypeMissmatchError.wrong_type_encountered(data, "?", self.type_tree.data)

        instance_group = self.require_own_group()
        for member_name, member_type_tree in self.type_tree.children.items():
            RegistryPersistor(instance_group, member_name, member_type_tree).save(
                getattr(data, member_name)
            )

    def _load(self) -> attrs.AttrsInstance:
        attrs_class = self.type_tree.data

        assert attrs.has(attrs_class)

        return attrs_class(
            **{
                member_name.strip("_"): RegistryPersistor(
                    self.group, member_name, member_type_tree
                ).load()
                for member_name, member_type_tree in self.type_tree.children.items()
            }
        )


@RegistryPersistor.register_persistor
class NumpyPersistor(core.Persistor):
    """
    Persists numpy arrays/scalars
    """

    @classmethod
    def is_applicable(cls, __type: core.TypeLike) -> bool:
        return core.is_ndarray(__type) or core.is_subclass(__type, np.generic)

    def _save(self, data: t.Any) -> None:
        if not isinstance(data, (np.ndarray, np.generic)):
            raise core.TypeMissmatchError.wrong_type_encountered(data, "?", np.ndarray)

        self.create_own_dataset(data=data)

    def _load(self) -> t.Any:
        should_be_np = self.dataset[()]

        self.assert_not_empty(should_be_np)

        return should_be_np
