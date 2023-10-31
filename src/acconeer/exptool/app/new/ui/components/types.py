# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import typing as t

from .pidgets import PidgetFactory, PidgetGroup


PidgetFactoryMapping = t.Mapping[str, PidgetFactory]
PidgetGroupFactoryMapping = t.Mapping[PidgetGroup, PidgetFactoryMapping]
