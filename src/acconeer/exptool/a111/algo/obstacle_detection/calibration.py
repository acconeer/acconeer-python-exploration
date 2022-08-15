# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import logging
from typing import List, Optional, Union

import attr
import yaml

import acconeer.exptool as et
from acconeer.exptool.a111 import algo


log = logging.getLogger(__name__)


def list_flattener(list_or_num: Union[list, float]):
    if isinstance(list_or_num, list):
        if len(list_or_num) != 1:
            raise ValueError(f"argument {list_or_num} needs to be a length 1 list or a number.")
        return list_or_num[0]
    return list_or_num


has_float_elements = attr.validators.deep_iterable(attr.validators.instance_of(float), None)


@attr.frozen
class ObstacleDetectionCalibration(algo.Calibration):
    """
    Calibration for obstacle detector.

    Supports to be loaded from ".yaml" files.
    """

    static_pwl_dist: List[float] = attr.ib(validator=has_float_elements)
    static_pwl_amp: List[float] = attr.ib(validator=has_float_elements)
    moving_pwl_dist: List[float] = attr.ib(validator=has_float_elements)
    moving_pwl_amp: List[float] = attr.ib(validator=has_float_elements)
    static_adjacent_factor: Union[float, List[float]] = attr.ib(
        validator=attr.validators.instance_of(float),
        converter=attr.converters.pipe(list_flattener, float),
    )
    moving_max: Union[float, List[float]] = attr.ib(
        validator=attr.validators.instance_of(float),
        converter=attr.converters.pipe(list_flattener, float),
    )

    @static_pwl_dist.validator
    @static_pwl_amp.validator
    def check_static_list(self, attribute, list_o_floats):
        if len(list_o_floats) != 5:
            raise ValueError(f"{attribute.name} is supposed have length = 5 ")

    @moving_pwl_dist.validator
    @moving_pwl_amp.validator
    def check_moving_list(self, attribute, list_o_floats):
        if attribute.name.startswith("moving") and len(list_o_floats) != 2:
            raise ValueError(f"{attribute.name} is supposed have length = 2 ")

    def save(self, path: algo._Path):
        self.validate_path(path)

        with open(path, "w") as stream:
            yaml.dump(
                dict(
                    static_pwl_dist=self.static_pwl_dist,
                    static_pwl_amp=self.static_pwl_amp,
                    moving_pwl_dist=self.moving_pwl_dist,
                    moving_pwl_amp=self.moving_pwl_amp,
                    static_adjacent_factor=self.static_adjacent_factor,
                    moving_max=self.moving_max,
                ),
                stream=stream,
                default_flow_style=False,
            )

    @classmethod
    def load(cls, path: algo._Path) -> algo.Calibration:
        cls.validate_path(path)

        with open(path, "r") as stream:
            calibration_dict = yaml.safe_load(stream)

        return cls(**calibration_dict)

    @classmethod
    def file_extensions(cls) -> algo._AcceptedFileExtensions:
        return [("yaml", "YAML files (*.yaml)")]


class ObstacleDetectionCalibrationConfiguration(et.configbase.Config):
    VERSION = 1

    static_adjacent_factor = et.configbase.FloatParameter(
        label="Static adjacent factor",
        default_value=0.0,
        limits=(0, None),
        decimals=6,
        order=0,
    )

    moving_max = et.configbase.FloatParameter(
        label="Moving max",
        default_value=0.0,
        limits=(0, None),
        decimals=6,
        order=10,
    )

    static_pwl_dist_1 = et.configbase.FloatParameter(
        label="Static PWL distance 1",
        default_value=0.0,
        limits=(0, None),
        decimals=6,
        order=20,
    )
    static_pwl_dist_2 = et.configbase.FloatParameter(
        label="Static PWL distance 2",
        default_value=0.0,
        limits=(0, None),
        decimals=6,
        order=21,
    )
    static_pwl_dist_3 = et.configbase.FloatParameter(
        label="Static PWL distance 3",
        default_value=0.0,
        limits=(0, None),
        decimals=6,
        order=22,
    )
    static_pwl_dist_4 = et.configbase.FloatParameter(
        label="Static PWL distance 4",
        default_value=0.0,
        limits=(0, None),
        decimals=6,
        order=23,
    )
    static_pwl_dist_5 = et.configbase.FloatParameter(
        label="Static PWL distance 5",
        default_value=0.0,
        limits=(0, None),
        decimals=6,
        order=24,
    )

    static_pwl_amp_1 = et.configbase.FloatParameter(
        label="Static PWL amplitude 1",
        default_value=0.0,
        limits=(0, None),
        decimals=6,
        order=30,
    )
    static_pwl_amp_2 = et.configbase.FloatParameter(
        label="Static PWL amplitude 2",
        default_value=0.0,
        limits=(0, None),
        decimals=6,
        order=31,
    )
    static_pwl_amp_3 = et.configbase.FloatParameter(
        label="Static PWL amplitude 3",
        default_value=0.0,
        limits=(0, None),
        decimals=6,
        order=32,
    )
    static_pwl_amp_4 = et.configbase.FloatParameter(
        label="Static PWL amplitude 4",
        default_value=0.0,
        limits=(0, None),
        decimals=6,
        order=33,
    )
    static_pwl_amp_5 = et.configbase.FloatParameter(
        label="Static PWL amplitude 5",
        default_value=0.0,
        limits=(0, None),
        decimals=6,
        order=34,
    )

    moving_pwl_dist_1 = et.configbase.FloatParameter(
        label="Moving PWL distance 1",
        default_value=0.0,
        limits=(0, None),
        decimals=6,
        order=40,
    )
    moving_pwl_dist_2 = et.configbase.FloatParameter(
        label="Moving PWL distance 2",
        default_value=0.0,
        limits=(0, None),
        decimals=6,
        order=41,
    )

    moving_pwl_amp_1 = et.configbase.FloatParameter(
        label="Moving PWL amplitude 1",
        default_value=0.0,
        limits=(0, None),
        decimals=6,
        order=50,
    )
    moving_pwl_amp_2 = et.configbase.FloatParameter(
        label="Moving PWL amplitude 2",
        default_value=0.0,
        limits=(0, None),
        decimals=6,
        order=51,
    )


class ObstacleDetectionCalibrationMapper(algo.CalibrationMapper):
    @classmethod
    def get_updated_calibration_from_configuration(
        cls,
        configuration: ObstacleDetectionCalibrationConfiguration,
        calibration: Optional[ObstacleDetectionCalibration],
    ) -> ObstacleDetectionCalibration:
        """
        Creates a new calibration given a configuration and (optionally) a calibration.

        The calibration is optional in order to allow for unsymmetric mapping between
        CalibrationConfiguration and Calibration, where fields not covered by the
        CalibrationConfiguration are copies from the Calibration. (see CalibrationMapper)
        """

        return ObstacleDetectionCalibration(
            static_pwl_dist=[
                configuration.static_pwl_dist_1,
                configuration.static_pwl_dist_2,
                configuration.static_pwl_dist_3,
                configuration.static_pwl_dist_4,
                configuration.static_pwl_dist_5,
            ],
            static_pwl_amp=[
                configuration.static_pwl_amp_1,
                configuration.static_pwl_amp_2,
                configuration.static_pwl_amp_3,
                configuration.static_pwl_amp_4,
                configuration.static_pwl_amp_5,
            ],
            moving_pwl_dist=[
                configuration.moving_pwl_dist_1,
                configuration.moving_pwl_dist_2,
            ],
            moving_pwl_amp=[
                configuration.moving_pwl_amp_1,
                configuration.moving_pwl_amp_2,
            ],
            static_adjacent_factor=configuration.static_adjacent_factor,
            moving_max=configuration.moving_max,
        )

    @classmethod
    def update_config_from_calibration(
        cls,
        configuration: ObstacleDetectionCalibrationConfiguration,
        calibration: ObstacleDetectionCalibration,
    ) -> None:
        """
        Updates fields of CalibrationConfiguration given a ObstacleDetectionCalibration
        """
        s_dist = calibration.static_pwl_dist
        configuration.static_pwl_dist_1 = s_dist[0]
        configuration.static_pwl_dist_2 = s_dist[1]
        configuration.static_pwl_dist_3 = s_dist[2]
        configuration.static_pwl_dist_4 = s_dist[3]
        configuration.static_pwl_dist_5 = s_dist[4]

        s_amp = calibration.static_pwl_amp
        configuration.static_pwl_amp_1 = s_amp[0]
        configuration.static_pwl_amp_2 = s_amp[1]
        configuration.static_pwl_amp_3 = s_amp[2]
        configuration.static_pwl_amp_4 = s_amp[3]
        configuration.static_pwl_amp_5 = s_amp[4]

        m_dist = calibration.moving_pwl_dist
        configuration.moving_pwl_dist_1 = m_dist[0]
        configuration.moving_pwl_dist_2 = m_dist[1]

        m_amp = calibration.moving_pwl_amp
        configuration.moving_pwl_amp_1 = m_amp[0]
        configuration.moving_pwl_amp_2 = m_amp[1]

        configuration.moving_max = calibration.moving_max
        configuration.static_adjacent_factor = calibration.static_adjacent_factor
