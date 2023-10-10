# Copyright (c) Acconeer AB, 2023
# All rights reserved

from __future__ import annotations

import attrs
import numpy as np

from acconeer.exptool.a121.algo.obstacle._processors import (
    Target,
)


@attrs.frozen(kw_only=True)
class BilateratorResult:
    beta_degs: list[float] = attrs.field()  # Bilateration angle
    velocities_m_s: list[float] = attrs.field()
    distances_m: list[float] = attrs.field()


DISTANCE_LIMIT_FACTOR = 1.2


class Bilaterator:
    """
    Bilateration class that aggregates the output from two obstacle detectors

    The convention is positive bilateration angle if the distance is greater
    to the second sensor.
    """

    def __init__(self, sensor_seperation: float):
        self.sensor_seperation = sensor_seperation

    def process(
        self, target_list_1: list[Target], target_list_2: list[Target]
    ) -> BilateratorResult:

        if not target_list_1 or not target_list_2:
            return BilateratorResult(beta_degs=[], velocities_m_s=[], distances_m=[])

        dist_diff = target_list_2[0].distance - target_list_1[0].distance
        dist_mean = (target_list_1[0].distance + target_list_2[0].distance) / 2
        velocity_mean = (target_list_1[0].velocity + target_list_2[0].velocity) / 2

        if np.abs(dist_diff) > DISTANCE_LIMIT_FACTOR * self.sensor_seperation:
            # Unreasonable distance difference
            return BilateratorResult(beta_degs=[], velocities_m_s=[], distances_m=[])

        if dist_diff > self.sensor_seperation:
            beta_deg = 90
        elif dist_diff < -self.sensor_seperation:
            beta_deg = -90
        else:
            beta_deg = 180 / np.pi * np.arcsin(dist_diff / self.sensor_seperation)

        return BilateratorResult(
            beta_degs=[beta_deg], velocities_m_s=[velocity_mean], distances_m=[dist_mean]
        )
