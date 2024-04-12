# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved
from __future__ import annotations

import logging
import typing as t

import h5py

from . import core
from .registry_persistor import RegistryPersistor


_T = t.TypeVar("_T")
_LOG = logging.getLogger(__name__)


def serialize(
    instance: t.Any, group: h5py.Group, *, override_type: t.Optional[core.TypeLike] = None
) -> None:
    """
    Serialize and save an arbitrary object to the specified group
    """
    type_tree = core.create_type_tree(override_type or type(instance))
    core.sanitize_instance(instance, type_tree)
    RegistryPersistor(group, "./", type_tree).save(instance)


def deserialize(group: h5py.Group, typ: t.Type[_T]) -> _T:
    """
    Load and deserialize an object of type 'typ' from the specified group

    Will raise an exception if anything goes wrong.
    """
    type_tree = core.create_type_tree(typ)
    loaded = RegistryPersistor(group, "./", type_tree).load()
    core.sanitize_instance(loaded, type_tree)

    return loaded  # type: ignore[no-any-return]


def try_deserialize(group: h5py.Group, typ: t.Type[_T]) -> t.Optional[_T]:
    """
    Like deserialize, but returns None instead of an raising an exception when an error occurs.
    """
    try:
        loaded = deserialize(group, typ)
    except Exception as e:
        _LOG.info(
            f"Could not deserialize a {typ.__name__} from {group} due to exception: '{e!s}'."
        )
        return None
    else:
        return loaded


register_persistor = RegistryPersistor.register_persistor


def register_json_presentable(__class: t.Type[core.JsonPresentable]) -> None:
    """
    Register a JSON presentable class (class with 'to_json' & 'from_json')

    Instances of this type will be saved as a JSON string.

    This can be called many times with the same type without repercussions.
    """
    RegistryPersistor.register_persistor(core.Persistor.from_json_presentable(__class))
