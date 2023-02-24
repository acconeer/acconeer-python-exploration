# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

from typing import Mapping

from .pidgets import ParameterWidgetFactory, PidgetGroup


PidgetFactoryMapping = Mapping[str, ParameterWidgetFactory]
PidgetGroupFactoryMapping = Mapping[PidgetGroup, PidgetFactoryMapping]
