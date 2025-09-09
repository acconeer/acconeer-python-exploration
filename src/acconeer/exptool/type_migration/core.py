# Copyright (c) Acconeer AB, 2024-2025
# All rights reserved

"""
The core of this module is the Node class, which has a type-safe[1]
builder-API to build a "migration tree" from the leaves and up.

An instance of Node can be seen as a node and the node data is a
python type (called 'head').
Each node keeps edges from its children to itself (called 'inbounds').
Children are also Nodes.

Here are some side-by-sides with timeline definitions and the migration tree:

=================================================================================
| Definition                                         | Migration tree           |
=================================================================================
|                                                    |                          |
|                                                    |                          |
| tm.start(int)                                      |  (h=int) <=top           |
|                                                    |                          |
|                                                    |                          |
|----------------------------------------------------|--------------------------|
|                                                    |  (h=int) <=top           |
| tm.start(int)                                      |     ^                    |
|   .load(str, lambda s: int(s), fail=...)           |     | via the lambda     |
|                                                    |     |                    |
|                                                    |  (h=str)                 |
|----------------------------------------------------|--------------------------|
|                                                    |  (h=int) <=top           |
| tm.start(int)                                      |    ^ ^                   |
|   .load(str, lambda s: int(s), fail=...)           |    | |                   |
|   .load(float, lambda s: int(s), fail=...)         |    | +-------+           |
|                                                    |    |         |           |
|                                                    |  (h=str)  (h=float)      |
|----------------------------------------------------|--------------------------|
|  tm.start(int)                                     |  (h=bytes) <=top         |
|    .load(str, lambda s: int(s), fail=...)          |     ^                    |
|    .load(float, lambda s: int(s), fail=...)        |     |                    |
|    .epoch(byte, lambda i: bytes(i), fail=...)      |     |                    |
|                                                    |  (h=int)                 |
|                                                    |    ^ ^                   |
|                                                    |    | |                   |
|                                                    |    | +-------+           |
|                                                    |    |         |           |
|                                                    |  (h=str)  (h=float)      |
|----------------------------------------------------|--------------------------|
|                                                    |  (h=bytes) <=top         |
|  tm.start(int)                                     |     ^ ^                  |
|    .load(str, lambda s: int(s), fail=...)          |     | |                  |
|    .load(float, lambda s: int(s), fail=...         |     | +------+           |
|    .epoch(byte, lambda i: bytes(i), fail=...)      |     |        |           |
|    .load(str,                                      |  (h=int)  (h=str)        |
|          lambda s: bytes(s, encoding="ascii"),     |    ^ ^                   |
|          fail=...)                                 |    | |                   |
|                                                    |    | +-------+           |
|                                                    |    |         |           |
|                                                    |  (h=str)  (h=float)      |
|----------------------------------------------------|--------------------------|

When calling 'migrate', a depth-first-search is done in the
tree to find a matching node for the type of the passed 'obj'.

When a matching Node is found, the "edge" function to the parent node then applied
for each level of the tree until the root is found. If the "edge" function raises
one of the Exceptions specified in 'fail', the search continues in the tree.
If an "edge" function raises and error that is not specified in 'fail', that
exception will be propagated.

If this search fails, a MigrateError is thrown, otherwise a migrated instance of
correct type is returned.

[1] type-safe practically means your editor will yell at you for using the wrong types
"""

from __future__ import annotations

import typing as t

import attrs
import attrs.validators as av
import exceptiongroup as eg
import typing_extensions as te


_T = t.TypeVar("_T")
_R = t.TypeVar("_R")
_S = t.TypeVar("_S")
_P = te.ParamSpec("_P")

_ReqCtxT = t.TypeVar("_ReqCtxT")
_NewCtxT = t.TypeVar("_NewCtxT")
_MigT_contra = t.TypeVar("_MigT_contra", contravariant=True)
_HeadT = t.TypeVar("_HeadT")

Completer: te.TypeAlias = t.Callable[[t.Type[_T]], _T]
_Transform: te.TypeAlias = t.Callable[[_T, Completer[_ReqCtxT]], _R]


def _wrap_with_ignored_completer(f: t.Callable[[_T], _R]) -> _Transform[_T, te.Never, _R]:
    """Turns a regular function into a _Transform for homogenous internal representation.
    Used in the non-contextual 'load' and 'epoch'
    """
    if not callable(f):
        msg = "f must be a callable"
        raise TypeError(msg)

    def wrapper(__x: _T, _: Completer[t.Any]) -> _R:
        return f(__x)

    return wrapper


def _flip(f: t.Callable[[_S, _T], _R]) -> t.Callable[[_T, _S], _R]:
    """Flips the parameters of a 2-parameter function"""

    def wrapper(__x: _T, __y: _S) -> _R:
        return f(__y, __x)

    return wrapper


def _null_completer(typ: type) -> t.Any:
    msg = f"No completion for {typ}"
    raise RuntimeError(msg)


class MigrationError(Exception):
    """This error is raised then a migration fails"""


class MigrationErrorGroup(MigrationError, eg.ExceptionGroup[Exception]):
    """A tree of errors describing why a migration failed"""


def _inbounds_validator(_ignored1: t.Any, _ignored2: t.Any, value: t.Any) -> None:
    (transform, fails, ancestor) = value

    if not callable(transform):
        msg = "The first element of the tuple needs to be a callable"
        raise TypeError(msg)

    if not isinstance(fails, t.Sequence):
        msg = "The second element of the tuple needs to be a sequence"
        raise TypeError(msg)

    if not all(issubclass(x, Exception) for x in fails):
        msg = "All elements of the fail sequence needs to be a subclass of BaseExceptions"
        raise TypeError(msg)

    if not isinstance(ancestor, Node):
        msg = "The third element of the tuple needs to be an Node"
        raise TypeError(msg)


@attrs.frozen(kw_only=True)
class Node(t.Generic[_HeadT, _ReqCtxT, _MigT_contra]):
    """
    A single node in a timeline. The type parameters are

    - _HeadT:       The type this timeline will migrate to.
                    I.e. the most recent version of a class.
    - _ReqCtxT:     The context that might be needed to migrate to '_HeadT'.
                    This is always 'Never' unless 'contextual_load'
                    or 'contextual_epoch' is used.
    - _MigT_contra: The type (usually a 'Union') this timeline is capable of migrating
                    to '_HeadT'.
    """

    head: type[_HeadT] = attrs.field(validator=av.instance_of(type))
    is_epoch: bool
    inbounds: t.Sequence[
        tuple[
            _Transform[t.Any, t.Any, _HeadT],
            t.Sequence[type[Exception]],
            Node[t.Any, t.Any, t.Any],
        ],
    ] = attrs.field(validator=av.deep_iterable(_inbounds_validator))

    def _is_supported(self, typ: type) -> bool:
        return issubclass(typ, self.head) or any(
            ancestor._is_supported(typ) for _, _, ancestor in self.inbounds
        )

    def _node_flatiter(self) -> t.Iterator[Node[t.Any, t.Any, t.Any]]:
        yield self
        for _, _, ancestor in self.inbounds:
            yield from ancestor._node_flatiter()

    def _get_epoch_node_head_types(self) -> set[type]:
        return set(node.head for node in self._node_flatiter() if node.is_epoch)

    def _get_epoch_node_with_head_type(
        self, head_type: type[_T]
    ) -> t.Optional[Node[_T, t.Any, t.Any]]:
        for node in self._node_flatiter():
            if not node.is_epoch:
                continue
            if node.head is head_type:
                return node

        return None

    def load(
        self,
        src: type[_T],
        f: t.Callable[[_T], _HeadT],
        fail: t.Sequence[type[Exception]],
    ) -> Node[_HeadT, _ReqCtxT, _MigT_contra | _T]:
        """Add a loading function to the current epoch"""
        new_gen: Node[_T, te.Never, te.Never] = Node(head=src, is_epoch=False, inbounds=[])
        return Node(
            head=self.head,
            is_epoch=self.is_epoch,
            inbounds=[(_wrap_with_ignored_completer(f), fail, new_gen), *self.inbounds],
        )

    def contextual_load(
        self,
        src: type[_T],
        f: _Transform[_T, _NewCtxT, _HeadT],
        fail: t.Sequence[type[Exception]],
    ) -> Node[_HeadT, _ReqCtxT | _NewCtxT, _MigT_contra | _T]:
        """
        Add a contextual loading function to the current epoch.
        `f`'s second argument should be a `Completer`
        """
        new_gen: Node[_T, te.Never, te.Never] = Node(head=src, is_epoch=False, inbounds=[])
        return Node(
            head=self.head,
            is_epoch=self.is_epoch,
            inbounds=[(f, fail, new_gen), *self.inbounds],
        )

    def epoch(
        self,
        typ: type[_T],
        f: t.Callable[[_HeadT], _T],
        fail: t.Sequence[type[Exception]],
    ) -> Node[_T, _ReqCtxT, _MigT_contra | _HeadT]:
        """Append an epoch to the timeline, adding a level to the migration tree"""
        return Node(
            head=typ,
            is_epoch=True,
            inbounds=[(_wrap_with_ignored_completer(f), fail, self)],
        )

    def contextual_epoch(
        self,
        typ: type[_T],
        f: _Transform[_HeadT, _NewCtxT, _T],
        fail: t.Sequence[type[Exception]],
    ) -> Node[_T, _ReqCtxT | _NewCtxT, _MigT_contra | _HeadT]:
        """Append a contextual epoch to the timeline, adding a level to the migration tree"""
        return Node(
            head=typ,
            is_epoch=True,
            inbounds=[(f, fail, self)],
        )

    def _migrate(
        self,
        obj: _HeadT | _MigT_contra,
        completer: Completer[_ReqCtxT],
    ) -> _HeadT:
        if isinstance(obj, self.head):
            return obj

        if len(self.inbounds) == 0:
            msg = f"Leaf node with head type {self.head} could not migrate object of type {type(obj)}"
            raise MigrationError(msg)

        errors = []

        for transform, transform_fails, ancestor in self.inbounds:
            try:
                ancestor_migrated = ancestor._migrate(obj, completer)
            except Exception as e:
                errors.append(e)
                continue

            try:
                self_migrated = transform(ancestor_migrated, completer)
            except tuple(transform_fails) as e:
                errors.append(e)
            else:
                return self_migrated

        msg = f"Failed migration to {self.head} from {obj!r}"
        raise MigrationErrorGroup(msg, tuple(errors))

    @te.overload
    def migrate(
        self: Node[_HeadT, te.Never, _MigT_contra], obj: _HeadT | _MigT_contra
    ) -> _HeadT: ...

    @te.overload
    def migrate(
        self: Node[_HeadT, te.Never, _MigT_contra],
        obj: _HeadT | _MigT_contra,
        *,
        target_type: type[_T],
    ) -> _T: ...

    @te.overload
    def migrate(
        self: Node[_HeadT, _ReqCtxT, _MigT_contra],
        obj: _HeadT | _MigT_contra,
        *,
        completer: Completer[_ReqCtxT],
    ) -> _HeadT: ...

    @te.overload
    def migrate(
        self: Node[_HeadT, _ReqCtxT, _MigT_contra],
        obj: _HeadT | _MigT_contra,
        *,
        completer: Completer[_ReqCtxT],
        target_type: type[_T],
    ) -> _T: ...

    def migrate(
        self,
        obj: _HeadT | _MigT_contra,
        *,
        completer: Completer[t.Any] = _null_completer,
        target_type: t.Optional[type[_T]] = None,
    ) -> t.Union[_HeadT, _T]:
        """
        Migrate `obj` be the type of the latest epoch or to `target_type` if `target_type` is an "epoch type".

        raises `MigrationError` if migration was not possible
        """
        if target_type is not None:
            target_node = self._get_epoch_node_with_head_type(target_type)

            if target_node is None:
                allowed_target_types = self._get_epoch_node_head_types()
                msg = f"Cannot migrate any object to {target_type}. It's not an epoch type in this tree. 'target_type' is allowed to be one of {allowed_target_types}"
                raise TypeError(msg)

            return target_node.migrate(obj, completer=completer)

        if not self._is_supported(type(obj)):
            msg = f"Cannot migrate objects of type {type(obj)}. It's not part of this tree."
            raise TypeError(msg)

        return self._migrate(obj, completer)

    def nop(self) -> te.Self:
        """Does nothing."""
        return self


def start(typ: type[_T]) -> Node[_T, te.Never, te.Never]:
    return Node(head=typ, is_epoch=True, inbounds=[])
