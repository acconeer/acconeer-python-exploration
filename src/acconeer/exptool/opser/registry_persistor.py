# Copyright (c) Acconeer AB, 2023-2025
# All rights reserved
from __future__ import annotations

import typing as t

from . import core


class RegistryPersistor(core.Persistor):
    """
    Persistor implementation that can have other persistors registered to it.

    Its 'save' and 'load' implementations exclusively call registered persistor's
    'save' and 'load'.

    This persistor is the hub for recursion and allows circumventing
    the combinatorial explosion of the problem.
    """

    _REGISTRY: t.ClassVar[t.Dict[str, t.Type[core.Persistor]]] = {}

    @classmethod
    def register_persistor(cls, __persistor: t.Type[core.Persistor]) -> t.Type[core.Persistor]:
        """
        Registers a persistor that can extend the handled types.

        This can be called many times with the same persistor without repercussions.
        """
        cls._REGISTRY[__persistor.__name__] = __persistor
        return __persistor

    @classmethod
    def priority_higher_than(cls, __persistor: t.Type[core.Persistor]) -> int:
        """Returns a priority that is higher than the priority of the specified persistor."""
        try:
            return cls._REGISTRY[__persistor.__name__].PRIORITY + 1
        except KeyError:
            msg = f"Persistor {__persistor} is not in the registry"
            raise RuntimeError(msg)

    @classmethod
    def _get_applicable_persistors(cls, __type: type) -> t.List[t.Type[core.Persistor]]:
        """Retrieves the persistors that can handle the specified type"""
        return sorted(
            (persistor for persistor in cls._REGISTRY.values() if persistor.is_applicable(__type)),
            key=lambda p: p.PRIORITY,
            reverse=True,
        )

    @classmethod
    def registry_size(cls) -> int:
        return len(cls._REGISTRY)

    @classmethod
    def is_applicable(cls, __type: core.TypeLike) -> bool:
        return len(cls._get_applicable_persistors(__type)) > 0

    def _save(self, instance: t.Any) -> None:
        persistor_classes = self._get_applicable_persistors(self.type_tree.data)

        if not persistor_classes:
            msg = f"No applicable persistors for instance {instance!r:.100}"
            raise core.SaveError(msg)

        errors = []
        for persistor_class in persistor_classes:
            try:
                persistor_class(self.parent_group, self.name, self.type_tree).save(instance)
            except core.SaveError as save_error:
                errors += [save_error]
                continue
            else:
                return

        msg = f"Could not save instance of type '{type(instance)}' (with expected type {self.type_tree.data}) using any of the persistors {persistor_classes}."
        raise core.SaveErrorGroup(
            msg,
            errors,
        )

    def _load(self) -> t.Any:
        persistor_classes = self._get_applicable_persistors(self.type_tree.data)

        if not persistor_classes:
            msg = f"No applicable persistors for expected type {self.type_tree.data}"
            raise core.LoadError(msg)

        errors = []
        for persistor_class in persistor_classes:
            try:
                res = persistor_class(self.parent_group, self.name, self.type_tree).load()
            except core.LoadError as load_error:
                errors += [load_error]
                continue
            else:
                return res

        msg = f"Could not load an instance of type {self.type_tree.data} with any of the persistors {persistor_classes}."
        raise core.LoadErrorGroup(
            msg,
            errors,
        )
