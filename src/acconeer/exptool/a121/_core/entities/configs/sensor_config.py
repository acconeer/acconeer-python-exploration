# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import contextlib
import json
import warnings
from typing import Any, Iterator, Optional, Type, TypeVar, Union, overload

import numpy as np

from acconeer.exptool.a121._core import utils

from .config_enums import PRF, IdleState, Profile
from .subsweep_config import SubsweepConfig
from .validation_error import ValidationError, ValidationResult, ValidationWarning


T = TypeVar("T")

_TOO_MANY_SUBSWEEPS_ERROR_FORMAT = (
    "SensorConfig has too many subsweeps "
    + 'to use accessor "{}". Number of subsweeps needs to be 1.'
)


class SubsweepProxyProperty(utils.ProxyProperty[T]):
    def __init__(self, prop: Any) -> None:
        super().__init__(
            accessor=lambda sensor_config: sensor_config.subsweep,
            prop=prop,
        )

    @contextlib.contextmanager
    def _more_helpful_accessor_errors(self) -> Iterator[None]:
        try:
            yield
        except AttributeError:
            # this should only be None if "property" isn't used as a decorator
            # "fget" is the function that gets decorated with "@property"
            # while "fset" is the function that gets decorated with "@<property name>.setter"
            assert self._property.fget is not None

            raise AttributeError(
                _TOO_MANY_SUBSWEEPS_ERROR_FORMAT.format(self._property.fget.__name__)
            ) from None

    @overload
    def __get__(self, obj: None, objtype: Optional[Type] = ...) -> utils.ProxyProperty[T]:
        ...

    @overload
    def __get__(self, obj: Any, objtype: Optional[Type] = ...) -> T:
        ...

    def __get__(
        self,
        obj: Optional[Any],
        objtype: Optional[Type] = None,
    ) -> Union[T, utils.ProxyProperty[T]]:
        with self._more_helpful_accessor_errors():
            return super().__get__(obj, objtype)

    def __set__(self, obj: Any, value: T) -> None:
        with self._more_helpful_accessor_errors():
            return super().__set__(obj, value)


@utils.no_dynamic_member_creation
class SensorConfig:
    """Sensor configuration

    The sensor config represents a 1-1 mapping to the RSS service config.

    By default, the sensor config holds a single :class:`SubsweepConfig`. The parameters defined by
    the subsweep config, like :attr:`start_point`, can be accessed via the sensor config. If
    multiple subsweeps are used, those parameters must be accessed via their respective subsweep
    configs.

    For example, a sensor config can be created like this:

    .. code-block:: python

        SensorConfig(sweeps_per_frame=16, start_point=123)

    Note that the :attr:`start_point` is implicitly set in the underlying subsweep config. If you
    want to explicitly set the subsweep config(s), you can do

    .. code-block:: python

        SensorConfig(
            sweeps_per_frame=16,
            subsweeps=[
                SubsweepConfig(start_point=123),
            ],
        )

    Parameters can also be accessed via the class attributes:

    .. code-block:: python

        sensor_config = SensorConfig()
        sensor_config.sweeps_per_frame = 16
        sensor_config.start_point = 123

    If you want to use multiple subsweeps with this style of setting/getting the attributes, you
    can do like this:

    .. code-block:: python

        sensor_config = SensorConfig(num_subsweeps=3)
        sensor_config.sweeps_per_frame = 16
        sensor_config.subsweeps[0].start_point = 123

    .. note::

        The sensor config does not control on which sensor it should be run. That is handled by
        the :class:`SessionConfig`.

    :param subsweeps:
        The list of subsweeps to initialize with. May not be combined with ``num_subsweeps``.
    :param num_subsweeps:
        Initialize with a given number of subsweeps. May not be combined with ``subsweeps``.
    :raises ValueError: If ``subsweeps`` and ``num_subsweeps`` are both given.
    :raises ValueError: If the given list of ``subsweeps`` is empty.
    :raises ValueError: If subsweeps parameters are both given implicitly and via ``subsweeps``.
    """

    _subsweeps: list[SubsweepConfig]

    _sweeps_per_frame: int
    _sweep_rate: Optional[float]
    _frame_rate: Optional[float]
    _continuous_sweep_mode: bool
    _double_buffering: bool
    _inter_frame_idle_state: IdleState
    _inter_sweep_idle_state: IdleState

    start_point = SubsweepProxyProperty[int](SubsweepConfig.start_point)
    num_points = SubsweepProxyProperty[int](SubsweepConfig.num_points)
    step_length = SubsweepProxyProperty[int](SubsweepConfig.step_length)
    profile = SubsweepProxyProperty[Profile](SubsweepConfig.profile)
    hwaas = SubsweepProxyProperty[int](SubsweepConfig.hwaas)
    receiver_gain = SubsweepProxyProperty[int](SubsweepConfig.receiver_gain)
    enable_tx = SubsweepProxyProperty[bool](SubsweepConfig.enable_tx)
    enable_loopback = SubsweepProxyProperty[bool](SubsweepConfig.enable_loopback)
    phase_enhancement = SubsweepProxyProperty[bool](SubsweepConfig.phase_enhancement)
    prf = SubsweepProxyProperty[PRF](SubsweepConfig.prf)

    def __init__(
        self,
        *,
        subsweeps: Optional[list[SubsweepConfig]] = None,
        num_subsweeps: Optional[int] = None,
        sweeps_per_frame: int = 1,
        sweep_rate: Optional[float] = None,
        frame_rate: Optional[float] = None,
        continuous_sweep_mode: bool = False,
        double_buffering: bool = False,
        inter_frame_idle_state: IdleState = IdleState.DEEP_SLEEP,
        inter_sweep_idle_state: IdleState = IdleState.READY,
        start_point: Optional[int] = None,
        num_points: Optional[int] = None,
        step_length: Optional[int] = None,
        profile: Optional[Profile] = None,
        hwaas: Optional[int] = None,
        receiver_gain: Optional[int] = None,
        enable_tx: Optional[bool] = None,
        enable_loopback: Optional[bool] = None,
        phase_enhancement: Optional[bool] = None,
        prf: Optional[PRF] = None,
    ) -> None:
        if subsweeps is not None and num_subsweeps is not None:
            raise ValueError(
                "It is not allowed to pass both `subsweeps` and `num_subsweeps`. Choose one."
            )
        if subsweeps == []:
            raise ValueError("Cannot pass an empty `subsweeps` list.")

        no_subsweep_param_passed = (
            start_point is None
            and num_points is None
            and step_length is None
            and profile is None
            and hwaas is None
            and receiver_gain is None
            and enable_tx is None
            and enable_loopback is None
            and phase_enhancement is None
            and prf is None
        )
        if subsweeps is not None and not no_subsweep_param_passed:
            raise ValueError(
                "Combining 'subsweeps' and subsweep parameters is not allowed."
                + "Specify subsweep params in each 'SubsweepConfig' instead."
            )

        if subsweeps is None and num_subsweeps is None:
            num_subsweeps = 1

        if subsweeps is not None:
            self._subsweeps = subsweeps
        elif num_subsweeps is not None:
            self._subsweeps = [SubsweepConfig() for _ in range(num_subsweeps)]
        else:
            raise RuntimeError

        self.sweeps_per_frame = sweeps_per_frame
        self.sweep_rate = sweep_rate
        self.frame_rate = frame_rate
        self.continuous_sweep_mode = continuous_sweep_mode
        self.double_buffering = double_buffering
        self.inter_frame_idle_state = inter_frame_idle_state
        self.inter_sweep_idle_state = inter_sweep_idle_state

        # Init proxy attributes

        if hwaas is not None:
            self.hwaas = hwaas
        if start_point is not None:
            self.start_point = start_point
        if num_points is not None:
            self.num_points = num_points
        if step_length is not None:
            self.step_length = step_length
        if profile is not None:
            self.profile = profile
        if receiver_gain is not None:
            self.receiver_gain = receiver_gain
        if enable_tx is not None:
            self.enable_tx = enable_tx
        if enable_loopback is not None:
            self.enable_loopback = enable_loopback
        if phase_enhancement is not None:
            self.phase_enhancement = phase_enhancement
        if prf is not None:
            self.prf = prf

    @property
    def subsweep(self) -> SubsweepConfig:
        """Retrieves the sole ``SubsweepConfig``

        :raises AttributeError: If ``num_subsweeps`` > 1
        """
        if self.num_subsweeps > 1:
            raise AttributeError(_TOO_MANY_SUBSWEEPS_ERROR_FORMAT.format("subsweep"))

        return self.subsweeps[0]

    @property
    def subsweeps(self) -> list[SubsweepConfig]:
        """The list of subsweep configs"""

        return self._subsweeps

    @property
    def num_subsweeps(self) -> int:
        """The number of subsweep configs"""

        return len(self.subsweeps)

    def __eq__(self, other: Any) -> bool:
        return type(self) == type(other) and self.to_dict() == other.to_dict()

    def to_dict(self) -> dict[str, Any]:
        return {
            "sweep_rate": self.sweep_rate,
            "frame_rate": self.frame_rate,
            "continuous_sweep_mode": self.continuous_sweep_mode,
            "double_buffering": self.double_buffering,
            "inter_frame_idle_state": self.inter_frame_idle_state,
            "inter_sweep_idle_state": self.inter_sweep_idle_state,
            "sweeps_per_frame": self.sweeps_per_frame,
            "subsweeps": [subsweep.to_dict() for subsweep in self.subsweeps],
        }

    @classmethod
    def from_dict(cls, d: dict) -> SensorConfig:
        d = d.copy()
        d["subsweeps"] = [SubsweepConfig.from_dict(subsweep_d) for subsweep_d in d["subsweeps"]]
        return cls(**d)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), cls=utils.EntityJSONEncoder)

    @classmethod
    def from_json(cls, json_str: str) -> SensorConfig:
        return cls.from_dict(json.loads(json_str))

    def validate(self) -> None:
        """Performs self-validation and validation of its subsweep configs

        :raises ValidationError: If anything is invalid.
        """
        for validation_result in self._collect_validation_results():
            try:
                raise validation_result
            except ValidationWarning as vw:
                warnings.warn(vw.message)

    def _collect_validation_results(self) -> list[ValidationResult]:
        sensor_config_validate_results = (
            self._validate_continuous_sweep_mode()
            + self._validate_idle_states()
            + self._validate_sweep_and_frame_rate()
            + self._validate_required_buffer_usage()
        )
        subsweep_config_validate_results = []
        for subsweep in self.subsweeps:
            subsweep_config_validate_results.extend(subsweep._collect_validation_results())
        return sensor_config_validate_results + subsweep_config_validate_results

    def _validate_continuous_sweep_mode(self) -> list[ValidationResult]:
        if not self.continuous_sweep_mode:
            return []

        validation_results: list[ValidationResult] = []

        if self.frame_rate is not None:
            validation_results.append(
                ValidationError(
                    self,
                    "frame_rate",
                    "Frame rate must unset (`None`) to use continuous sweep mode.",
                )
            )
        if self.sweep_rate is None:
            validation_results.append(
                ValidationError(
                    self, "sweep_rate", "Sweep rate must be set to use continuous sweep mode."
                )
            )
        if self.inter_frame_idle_state != self.inter_sweep_idle_state:
            validation_results.extend(
                ValidationError(
                    self,
                    idle_state,
                    "Inter sweep/frame idle states must be equal to use continuous sweep mode.",
                )
                for idle_state in ["inter_frame_idle_state", "inter_sweep_idle_state"]
            )
        if self.sweeps_per_frame == 1:
            validation_results.append(
                ValidationWarning(
                    self,
                    "continuous_sweep_mode",
                    (
                        "Not meaningful with only 1 sweep per frame. A fixed frame rate can be "
                        "used instead."
                    ),
                )
            )
        return validation_results

    def _validate_idle_states(self) -> list[ValidationResult]:
        if not (
            self.inter_frame_idle_state.is_deeper_than(self.inter_sweep_idle_state)
            or self.inter_frame_idle_state == self.inter_sweep_idle_state
        ):
            return [
                ValidationError(
                    self,
                    idle_state,
                    "Inter frame idle state needs to be deeper "
                    + "or the same as inter sweep idle state",
                )
                for idle_state in ["inter_frame_idle_state", "inter_sweep_idle_state"]
            ]
        return []

    def _validate_sweep_and_frame_rate(self) -> list[ValidationResult]:
        validation_results: list[ValidationResult] = []

        if self.sweep_rate is not None and self.frame_rate is not None:
            seconds_needed_per_frame = self.sweeps_per_frame / self.sweep_rate

            if self.frame_rate > 1 / seconds_needed_per_frame:
                validation_results.append(
                    ValidationError(
                        self,
                        "frame_rate",
                        "The frame rate is set faster than what the sweep rate allows."
                        + f"Frame rate: {self.frame_rate} Hz\n"
                        + "Sweep rate / sweeps per frame: "
                        + f"{self.sweep_rate / self.sweeps_per_frame} Hz",
                    )
                )

            if np.isclose(self.frame_rate, 1 / seconds_needed_per_frame):
                validation_results.extend(
                    ValidationWarning(
                        self,
                        field,
                        "Frame rate is approximately equal to SPF / Sweep rate. "
                        + "Use continuous sweep mode instead.",
                    )
                    for field in ["sweep_rate", "frame_rate", "sweeps_per_frame"]
                )
        return validation_results

    def _validate_required_buffer_usage(self) -> list[ValidationResult]:
        BUFFER_SIZE = 4096
        ERROR_MSG = "This config would have required buffer size {}, but the max is {}"

        buffer_size_available = (
            (BUFFER_SIZE // 2) - 1 if self.double_buffering else BUFFER_SIZE - 1
        )
        total_num_points = sum(subsweep_config.num_points for subsweep_config in self.subsweeps)
        required_buffer_size = total_num_points * self.sweeps_per_frame

        validation_results: list[ValidationResult] = []

        if required_buffer_size > buffer_size_available:
            validation_results.append(
                ValidationError(
                    self,
                    "sweeps_per_frame",
                    ERROR_MSG.format(required_buffer_size, buffer_size_available),
                ),
            )
            validation_results.extend(
                ValidationError(
                    subsweep_config,
                    "num_points",
                    ERROR_MSG.format(required_buffer_size, buffer_size_available),
                )
                for subsweep_config in self.subsweeps
            )
        return validation_results

    @property
    def sweeps_per_frame(self) -> int:
        """Sweeps per frame (SPF)

        The number of sweeps that will be captured in each frame (measurement).

        Must be > 0.
        """

        return self._sweeps_per_frame

    @sweeps_per_frame.setter
    def sweeps_per_frame(self, value: int) -> None:
        int_value = utils.convert_validate_int(value, min_value=1)
        self._sweeps_per_frame = int_value

    @property
    def sweep_rate(self) -> Optional[float]:
        """Sweep rate

        The sweep rate for sweeps in a frame (measurement).

        In Hz. Must be > 0 or ``None``, where ``None`` is interpreted as max sweep rate.
        """

        return self._sweep_rate

    @sweep_rate.setter
    def sweep_rate(self, value: Optional[float]) -> None:
        if value is None:
            self._sweep_rate = None
        else:
            self._sweep_rate = utils.validate_float(value, min_value=0.0, inclusive=False)

    @property
    def frame_rate(self) -> Optional[float]:
        """Frame rate

        Setting the frame rate to unlimited means that the rate is not limited by the sensor but
        the rate that the host acknowledge and reads out the measurement data.

        In Hz. Must be > 0 or ``None``, where ``None`` is interpreted as unlimited.
        """

        return self._frame_rate

    @frame_rate.setter
    def frame_rate(self, value: Optional[float]) -> None:
        if value is None:
            self._frame_rate = None
        else:
            self._frame_rate = utils.validate_float(value, min_value=0.0, inclusive=False)

    @property
    def continuous_sweep_mode(self) -> bool:
        """Continuous sweep mode (CSM)

        With CSM, the sensor timing is set up to generate a continuous
        stream of sweeps, even if more than one sweep per frame is used.
        The interval between the last sweep in one frame to the first
        sweep in the next frame becomes equal to the interval between
        sweeps within a frame (given by the sweep rate).

        It ensures that:

        'frame rate' = 'sweep rate' / 'sweeps per frame'

        While the frame rate parameter can be set to approximately
        satisfy this condition, using CSM is more precise.

        If only one sweep per frame is used, CSM has no use since a
        continuous stream of sweeps is already given (if a fixed frame
        rate is used).

        The main use for CSM is to allow reading out data at a slower
        rate than the sweep rate, while maintaining that sweep rate
        continuously.

        Note that in most cases, double buffering must be enabled to
        allow high rates without delays.

        Constraints:

        - :attr:`frame_rate` must be set to unlimited (``None``).
        - :attr:`sweep_rate` must be set (> 0).
        - :attr:`inter_frame_idle_state` must be set equal to :attr:`inter_sweep_idle_state`.
        """

        return self._continuous_sweep_mode

    @continuous_sweep_mode.setter
    def continuous_sweep_mode(self, value: bool) -> None:
        self._continuous_sweep_mode = bool(value)

    @property
    def double_buffering(self) -> bool:
        """Double buffering

        If enabled, the sensor buffer will be split in two halves reducing the
        maximum number of samples. A frame can be read while sampling is done into the
        other buffer.
        """

        return self._double_buffering

    @double_buffering.setter
    def double_buffering(self, value: bool) -> None:
        self._double_buffering = bool(value)

    @property
    def inter_frame_idle_state(self) -> IdleState:
        """Inter frame idle state

        The inter frame idle state is the state the sensor idles in between each frame.

        Idle state `Deep sleep` is the deepest state where as much of the
        sensor hardware as possible is shut down and idle state `Ready` is
        the lightest state where most of the sensor hardware is kept on.

        `Deep sleep` is the slowest to transition from while `Ready` is the fastest.

        The :attr:`inter_frame_idle_state` of the frame must be deeper or
        the same as the :attr:`inter_sweep_idle_state` .
        """

        return self._inter_frame_idle_state

    @inter_frame_idle_state.setter
    def inter_frame_idle_state(self, value: IdleState) -> None:
        self._inter_frame_idle_state = IdleState(value)

    @property
    def inter_sweep_idle_state(self) -> IdleState:
        """Inter sweep idle state

        The inter sweep idle state is the state the sensor idles in
        between each sweep in a frame.

        Idle state `Deep sleep` is the deepest state where as much of the
        sensor hardware as possible is shut down and idle state `Ready` is
        the lightest state where most of the sensor hardware is kept on.

        `Deep sleep` is the slowest to transition from while `Ready` is the fastest.
        """

        return self._inter_sweep_idle_state

    @inter_sweep_idle_state.setter
    def inter_sweep_idle_state(self, value: IdleState) -> None:
        self._inter_sweep_idle_state = IdleState(value)

    def _pretty_str_lines(self, sensor_id: Optional[int] = None) -> list[str]:
        lines = []

        id_str = "" if sensor_id is None else f" @ sensor {sensor_id}"
        lines.append(f"{type(self).__name__}{id_str}:")

        d = self.to_dict()
        del d["subsweeps"]
        lines.extend(utils.pretty_dict_line_strs(d))

        lines.append("  subsweeps:")
        for i, subsweep in enumerate(self.subsweeps):
            ss_lines = subsweep._pretty_str_lines(index=i)
            lines.extend(utils.indent_strs(ss_lines, 2))

        return lines

    def __str__(self) -> str:
        return "\n".join(self._pretty_str_lines())
