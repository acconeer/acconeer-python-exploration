# Copyright (c) Acconeer AB, 2023
# All rights reserved

"""
This module provides classes for listing- & creating sessions
according to different "session schemas" (how sessions are laid out inside a H5 file).
"""

from __future__ import annotations

import itertools
import typing as t

import h5py


class SessionSchema:
    @staticmethod
    def _session_names() -> t.Iterator[str]:
        return (f"sessions/session_{i}" for i in itertools.count(start=0))

    @staticmethod
    def _aliased_group(file: h5py.File, session_name: str) -> t.Optional[h5py.Group]:
        if session_name == "sessions/session_0":
            return file.get("session")
        else:
            return None

    @classmethod
    def session_groups_on_disk(cls, file: h5py.File) -> t.Sequence[h5py.Group]:
        """Lists sessions in a h5 file"""
        return tuple(
            itertools.takewhile(
                lambda group: group is not None,
                (
                    file.get(name, default=cls._aliased_group(file, name))
                    for name in cls._session_names()
                ),
            )
        )

    @classmethod
    def create_next_session_group(cls, file: h5py.File) -> h5py.Group:
        """Creates a new session group in the h5 file."""
        next_name = next(itertools.dropwhile(lambda name: name in file, cls._session_names()))

        if next_name == "sessions/session_0":
            file["session"] = h5py.SoftLink("/sessions/session_0")

        return file.create_group(next_name)
