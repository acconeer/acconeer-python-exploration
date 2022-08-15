# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from typing import Mapping

from .pidgets import ParameterWidgetFactory


PidgetFactoryMapping = Mapping[str, ParameterWidgetFactory]
