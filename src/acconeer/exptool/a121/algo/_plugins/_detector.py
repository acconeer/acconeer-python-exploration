# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from typing import Generic, TypeVar

from ._a121 import A121BackendPluginBase, A121PlotPluginBase, A121ViewPluginBase


T = TypeVar("T")


class DetectorBackendPluginBase(Generic[T], A121BackendPluginBase[T]):
    pass


class DetectorPlotPluginBase(A121PlotPluginBase):
    pass


class DetectorViewPluginBase(A121ViewPluginBase):
    pass
