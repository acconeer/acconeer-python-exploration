# Copyright (c) Acconeer AB, 2023
# All rights reserved

"""
This module provides classes for listing- & creating sessions
according to different "session schemas" (how sessions are laid out inside a H5 file).
"""

from __future__ import annotations

import typing as t

import h5py


class SchemaError(Exception):
    pass


class SessionSchema:
    @classmethod
    def session_groups_on_disk(cls, file: h5py.File) -> t.Sequence[h5py.Group]:
        """Lists sessions in a h5 file"""
        return (file["session"],) if "session" in file else ()

    @classmethod
    def create_next_session_group(cls, file: h5py.File) -> h5py.Group:
        """
        Creates a new session group in the h5 file.

        :raises SchemaError: If there is no more valid session groups to be created
        """
        if "session" in file:
            raise SchemaError("'session' group already present. No more valid groups to create.")

        return file.create_group("session")
