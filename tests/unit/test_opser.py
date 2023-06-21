# Copyright (c) Acconeer AB, 2023
# All rights reserved
from __future__ import annotations

import sys
import typing as t
from pathlib import Path
from random import choice, random

import attrs
import h5py
import numpy as np
import numpy.typing as npt
import pytest

from acconeer.exptool import a121, opser
from acconeer.exptool.a121._core.entities import INT_16_COMPLEX, ResultContext
from acconeer.exptool.a121.algo import (
    bilateration,
    breathing,
    distance,
    phase_tracking,
    presence,
    smart_presence,
    surface_velocity,
    tank_level,
    touchless_button,
    vibration,
)
from acconeer.exptool.a121.algo.bilateration import _processor as bilateration_processor
from acconeer.exptool.a121.algo.breathing import _processor as breathing_processor
from acconeer.exptool.a121.algo.distance import _detector as distance_detector
from acconeer.exptool.a121.algo.distance import _processors as distance_processors
from acconeer.exptool.a121.algo.presence import _processors as presence_processors
from acconeer.exptool.a121.algo.smart_presence import _ref_app as smart_presence_ref_app
from acconeer.exptool.a121.algo.surface_velocity import _processor as surface_velocity_processor
from acconeer.exptool.a121.algo.tank_level import _processor as tank_level_processor
from acconeer.exptool.a121.algo.tank_level import _ref_app as tank_level_ref_app
from acconeer.exptool.opser.registry_persistor import RegistryPersistor


_T = t.TypeVar("_T")


opser.register_json_presentable(a121.SessionConfig)


def _list(element_type: type, length: int = 3) -> t.List[t.Any]:
    """Helper function for mock data. returns a list with elements of type `element_type`"""
    return [element_type(random()) for _ in range(length)]


def _array(dtype: t.Any, shape: tuple[int, ...] = (1, 2, 3)) -> npt.NDArray[t.Any]:
    """Helper function for mock data. returns an array with elements of type `element_type`"""
    return np.random.normal(shape).astype(dtype)


@attrs.frozen
class Simple:
    integer: int
    string: str


@attrs.define
class SimpleReversed:
    string: str
    integer: int


@attrs.define
class Parent:
    child: Simple
    a: float


@attrs.define
class OptionalParent:
    child: t.Optional[Simple]
    a: float


@attrs.define
class ExoticKeyDictParent:
    children: t.Dict[Simple, Simple]


@attrs.define
class ListOfInts:
    children: t.List[int]


@attrs.define
class ListParent:
    children: t.List[Simple]


@attrs.define
class DictParent:
    children: t.Dict[int, Simple]


@attrs.define
class TupleParent:
    children: t.Tuple[int, Simple, str]


@attrs.define
class UnionParent:
    child: t.Union[Simple, Parent]


@attrs.define
class ListOfListParent:
    children: t.List[t.List[Simple]]


@pytest.fixture
def tmp_h5_file(tmp_path: Path) -> t.Iterator[Path]:
    with h5py.File(tmp_path / "test_opser.h5", "w") as file:
        yield file


TEST = [
    Simple(42, "hello"),
    Parent(Simple(42, "hello"), 0.999),
    OptionalParent(Simple(42, "hello"), 0.999),
    OptionalParent(None, 0.999),
    ExoticKeyDictParent({Simple(42, "hello"): Simple(42, "hello")}),
    ListOfInts([1, 2, 3]),
    ListOfInts(list(range(50))),
    ListParent([Simple(42, "hello")]),
    DictParent({1: Simple(42, "hello")}),
    TupleParent((1, Simple(42, "hello"), "hi")),
    UnionParent(Simple(42, "hello")),
    UnionParent(Parent(Simple(42, "hello"), 0.999)),
    ListOfListParent([[Simple(42, "hello")]]),
]


MOCK_SERVICE_RESULT = a121.Result(
    data_saturated=False,
    frame_delayed=True,
    calibration_needed=False,
    temperature=10,
    frame=_array(INT_16_COMPLEX),
    tick=1337,
    context=ResultContext(
        metadata=a121.Metadata(
            frame_data_length=10,
            sweep_data_length=11,
            subsweep_data_offset=_array(np.int_),
            subsweep_data_length=_array(np.int_),
            calibration_temperature=13,
            tick_period=123,
            base_step_length_m=500.0,
            max_sweep_rate=10000.0,
            high_speed_mode=False,
        ),
        ticks_per_second=10,
    ),
)


BILATERATION = [
    bilateration.ProcessorConfig(sensor_spacing_m=25.0),
    bilateration.ProcessorResult(points=[], objects_without_counterpart=[]),
    bilateration.ProcessorResult(
        points=[
            bilateration_processor.Point(
                angle=random(),
                distance=random(),
                x_coord=random(),
                y_coord=random(),
            )
        ],
        objects_without_counterpart=[
            bilateration_processor.ObjectWithoutCounterpart(
                distance=random(),
                sensor_position="hello",
            )
        ],
    ),
]


PRESENCE_PROCESSOR_EXTRA_RESULT = presence_processors.ProcessorExtraResult(
    frame=_array(np.complex_),
    abs_mean_sweep=_array(np.float_),
    fast_lp_mean_sweep=_array(np.float_),
    slow_lp_mean_sweep=_array(np.float_),
    lp_noise=_array(np.float_),
    presence_distance_index=10,
)


PRESENCE_PROCESSOR_RESULT = presence.ProcessorResult(
    intra_presence_score=random(),
    intra=_array(np.float_),
    inter_presence_score=random(),
    inter=_array(np.float_),
    presence_distance=random(),
    presence_detected=choice([True, False]),
    extra_result=PRESENCE_PROCESSOR_EXTRA_RESULT,
)

BREATHING = [
    breathing.RefAppConfig(start_m=0.55),
    breathing.RefAppResult(
        app_state=breathing.AppState.ESTIMATE_BREATHING_RATE,
        distances_being_analyzed=(1, 2),
        presence_result=PRESENCE_PROCESSOR_RESULT,
        breathing_result=breathing_processor.BreathingProcessorResult(
            breathing_rate=None,
            extra_result=breathing_processor.BreathingProcessorExtraResult(
                psd=_array(np.float_),
                frequencies=_array(np.float_),
                breathing_motion=_array(np.float_),
                time_vector=_array(np.float_),
                breathing_rate_history=_array(np.float_),
                all_breathing_rate_history=_array(np.float_),
            ),
        ),
    ),
]

DISTANCE_PROCESSOR_RESULT = distance.ProcessorResult(
    estimated_distances=_list(float),
    estimated_strengths=_list(float),
    near_edge_status=choice([False, True]),
    recorded_threshold_mean_sweep=_array(np.float_),
    recorded_threshold_noise_std=_list(np.float_),
    direct_leakage=_array(np.complex_),
    phase_jitter_comp_reference=_array(np.float_),
    extra_result=distance_processors.ProcessorExtraResult(),
)

DISTANCE_DETECTOR_RESULT = distance.DetectorResult(
    distances=_array(np.float_),
    strengths=None,
    near_edge_status=choice([False, True]),
    sensor_calibration_needed=False,
    temperature=13,
    processor_results=[DISTANCE_PROCESSOR_RESULT],
    service_extended_result=[{1: MOCK_SERVICE_RESULT}],
)

DISTANCE = [
    distance.DetectorConfig(start_m=100.0),
    distance.DetectorContext(
        single_sensor_contexts={
            1: distance_detector.SingleSensorContext(
                loopback_peak_location_m=random(),
                direct_leakage=_array(np.complex_),
                phase_jitter_comp_reference=_array(np.float_),
                recorded_thresholds_mean_sweep=[_array(np.float_) for _ in range(3)],
                recorded_thresholds_noise_std=[
                    [_array(np.float_) for _ in range(3)] for _ in range(3)
                ],
                bg_noise_std=[_list(float) for _ in range(3)],
                session_config_used_during_calibration=a121.SessionConfig(),
                reference_temperature=5,
                sensor_calibration=a121.SensorCalibration(temperature=5, data="hello there"),
                extra_context=distance_detector.SingleSensorExtraContext(),
            )
        }
    ),
    distance.DetectorContext(single_sensor_contexts={1: distance_detector.SingleSensorContext()}),
    DISTANCE_DETECTOR_RESULT,
    distance.ProcessorConfig(threshold_sensitivity=0.00001),
    distance.ProcessorContext(
        direct_leakage=_array(np.complex_),
        phase_jitter_comp_ref=_array(np.float_),
        recorded_threshold_mean_sweep=_array(np.float_),
        recorded_threshold_noise_std=_list(np.float_),
        bg_noise_std=[1.0, 2.0, 3.0],
        reference_temperature=5,
        loopback_peak_location_m=5.0,
    ),
    DISTANCE_PROCESSOR_RESULT,
    distance.ProcessorResult(),
]


PHASE_TRACKING = [
    phase_tracking.ProcessorConfig(threshold=0.0),
    phase_tracking.ProcessorContext(),  # empty
    phase_tracking.ProcessorResult(
        lp_abs_sweep=_array(np.float_),
        angle_sweep=_array(np.float_),
        threshold=None,
        rel_time_stamps=_array(np.float_),
        distance_history=_array(np.float_),
        peak_loc_m=13.37,
    ),
]

PRESENCE = [
    presence.ProcessorConfig(inter_phase_boost=True),
    presence.ProcessorResult(
        intra_presence_score=random(),
        intra=_array(np.float_),
        inter_presence_score=random(),
        inter=_array(np.float_),
        presence_distance=random(),
        presence_detected=choice([True, False]),
        extra_result=PRESENCE_PROCESSOR_EXTRA_RESULT,
    ),
    presence.DetectorConfig(start_m=1.0),
    presence.DetectorResult(
        intra_presence_score=10.0,
        intra_depthwise_scores=_array(np.float_),
        inter_presence_score=10.0,
        inter_depthwise_scores=_array(np.float_),
        presence_distance=10.0,
        presence_detected=False,
        processor_extra_result=PRESENCE_PROCESSOR_EXTRA_RESULT,
        service_result=MOCK_SERVICE_RESULT,
    ),
]


SURFACE_VELOCITY_PROCESSOR_EXTRA_RESULT = surface_velocity_processor.ProcessorExtraResult(
    max_bin_vertical_vs=_array(np.float_),
    peak_width=13.0,
    vertical_velocities=_array(np.float_),
    psd=_array(np.float_),
    peak_idx=np.int8(0),
    psd_threshold=_array(np.float_),
)

SURFACE_VELOCITY = [
    surface_velocity.ExampleAppConfig(surface_distance=2.0),
    surface_velocity.ExampleAppResult(
        velocity=random(),
        distance_m=random(),
        processor_extra_result=SURFACE_VELOCITY_PROCESSOR_EXTRA_RESULT,
        service_result=MOCK_SERVICE_RESULT,
    ),
    surface_velocity_processor.ProcessorConfig(),
    surface_velocity_processor.ProcessorResult(
        estimated_v=random(),
        distance_m=random(),
        extra_result=SURFACE_VELOCITY_PROCESSOR_EXTRA_RESULT,
    ),
    surface_velocity_processor.ProcessorContext(),  # empty
]

SMART_PRESENCE = [
    smart_presence.RefAppResult(
        zone_limits=_array(np.float_),
        presence_detected=choice([True, False]),
        max_presence_zone=4,
        total_zone_detections=_array(np.int_),
        inter_presence_score=random(),
        inter_zone_detections=_array(np.int_),
        max_inter_zone=None,
        intra_presence_score=random(),
        intra_zone_detections=_array(np.int_),
        max_intra_zone=4,
        used_config=smart_presence_ref_app._Mode.NOMINAL_CONFIG,
        wake_up_detections=None,
        switch_delay=choice([True, False]),
        service_result=MOCK_SERVICE_RESULT,
    ),
    smart_presence.RefAppConfig(wake_up_mode=False),
]

TANK_LEVEL_PROCESSOR_EXTRA_RESULT = tank_level_processor.ProcessorExtraResult(
    level_and_time_for_plotting={"hello": _array(np.float_)}
)

TANK_LEVEL = [
    tank_level.RefAppConfig(median_filter_length=55),
    # tank_level.RefAppContext <=> distance.DetectorContext. Already covered.
    tank_level.RefAppResult(
        peak_detected=None,
        peak_status=None,
        level=None,
        extra_result=tank_level_ref_app.RefAppExtraResult(
            processor_extra_result=TANK_LEVEL_PROCESSOR_EXTRA_RESULT,
            detector_result={42: DISTANCE_DETECTOR_RESULT},
        ),
    ),
    tank_level.RefAppResult(
        peak_detected=None,
        peak_status=tank_level.ProcessorLevelStatus.OUT_OF_RANGE,
        level=0.0,
        extra_result=tank_level_ref_app.RefAppExtraResult(
            processor_extra_result=TANK_LEVEL_PROCESSOR_EXTRA_RESULT,
            detector_result={42: DISTANCE_DETECTOR_RESULT},
        ),
    ),
    tank_level.ProcessorConfig(),
    tank_level.ProcessorResult(
        peak_detected=True,
        peak_status=tank_level_processor.ProcessorLevelStatus.NO_DETECTION,
        filtered_level=0.0,
        extra_result=TANK_LEVEL_PROCESSOR_EXTRA_RESULT,
    ),
    tank_level.ProcessorResult(
        peak_detected=None,
        peak_status=None,
        filtered_level=None,
        extra_result=TANK_LEVEL_PROCESSOR_EXTRA_RESULT,
    ),
]


TOUCHLESS_BUTTON = [
    touchless_button.ProcessorConfig(),
    touchless_button.ProcessorResult(
        detection_close=True,
        detection_far=False,
    ),
    touchless_button.ProcessorResult(
        detection_close=None,
        detection_far=None,
    ),
]


VIBRATION = [
    vibration.ProcessorConfig(),
    vibration.ProcessorContext(),  # empty
    vibration.ProcessorResult(
        result_available=True,
        time_series=_array(np.float_),
        lp_z_abs_db=_array(np.float_),
        freqs=_array(np.float_),
        max_amplitude=random(),
        amplitude_threshold=random(),
        max_psd_ampl=random(),
        max_psd_ampl_freq=random(),
    ),
    vibration.ProcessorResult(
        result_available=True,
        time_series=None,
        lp_z_abs_db=None,
        freqs=_array(np.float_),
        max_amplitude=random(),
        amplitude_threshold=random(),
        max_psd_ampl=None,
        max_psd_ampl_freq=None,
    ),
]


@pytest.mark.parametrize(
    "instance",
    [
        *TEST,
        *BILATERATION,
        *BREATHING,
        *DISTANCE,
        *PHASE_TRACKING,
        *PRESENCE,
        *SMART_PRESENCE,
        *SURFACE_VELOCITY,
        *TANK_LEVEL,
        *TOUCHLESS_BUTTON,
        *VIBRATION,
    ],
    ids=lambda i: type(i).__name__,
)
def test_equality(instance: t.Any, tmp_h5_file: h5py.File) -> None:
    opser.serialize(instance, tmp_h5_file)
    reconstructed = opser.deserialize(tmp_h5_file, type(instance))
    assert instance == reconstructed


def test_can_best_effort_handle_migration_from_optional(tmp_h5_file: h5py.File) -> None:
    old = OptionalParent(Simple(1, "1"), 0.1)
    opser.serialize(old, tmp_h5_file)
    loaded = opser.deserialize(tmp_h5_file, Parent)
    assert loaded.a == 0.1
    assert loaded.child == Simple(1, "1")


def test_cannot_handle_None_migration_from_optional(tmp_h5_file: h5py.File) -> None:
    old = OptionalParent(None, 0.1)
    opser.serialize(old, tmp_h5_file)
    with pytest.raises(opser.core.LoadError):
        _ = opser.deserialize(tmp_h5_file, Parent)


@attrs.define
class Recursive:
    r: Recursive


@attrs.define
class RecursiveList:
    r: t.List[RecursiveList]


@attrs.define
class RecursiveListOfDict:
    r: t.List[t.Dict[str, RecursiveListOfDict]]


@pytest.mark.parametrize("typ", [Recursive, RecursiveList, RecursiveListOfDict])
def test_cannot_construct_type_tree_for_recursive_types(typ: type) -> None:
    try:
        opser.core.create_type_tree(typ)
    except TypeError as error:
        assert "recursive" in str(error).lower()
    else:
        pytest.fail("TypeError was not raised")


@attrs.define
class AnnotatedWithBuiltinCollection:
    ints: list[int]


@pytest.mark.skipif(
    sys.version_info >= (3, 9), reason="It's fine to annotate with builtins on Python >=3.9"
)
def test_raises_error_if_type_is_annotated_with_builtins() -> None:
    with pytest.raises(TypeError):
        opser.core.create_type_tree(AnnotatedWithBuiltinCollection)


@pytest.mark.skipif(sys.version_info < (3, 9), reason="Should raise error on Python < 3.9")
def test_ok_to_annotated_with_builtins() -> None:
    _ = opser.core.create_type_tree(AnnotatedWithBuiltinCollection)


def test_sanity_generic_alias() -> None:
    assert type(t.List[int]) == t._GenericAlias


@attrs.define
class GenericClass(t.Generic[_T]):
    x: _T


@attrs.define
class SpecializedGenericClass(GenericClass[int]):
    pass


def test_serializing_an_instance_of_a_generic_class_is_not_implemented(
    tmp_h5_file: h5py.File,
) -> None:
    with pytest.raises(NotImplementedError):
        opser.serialize(GenericClass[int](x=1), tmp_h5_file)

    with pytest.raises(NotImplementedError):
        opser.serialize(SpecializedGenericClass(x=1), tmp_h5_file)


@attrs.define
class VariadicTupleParent:
    children: t.Tuple[int, ...]


def test_cannot_create_type_tree_for_class_with_variadic_tuple() -> None:
    with pytest.raises(NotImplementedError):
        _ = opser.core.create_type_tree(VariadicTupleParent)


def test_is_class() -> None:
    assert opser.core.is_class(Simple)
    assert opser.core.is_class(Parent)
    assert opser.core.is_class(GenericClass)
    assert opser.core.is_class(float)
    assert opser.core.is_class(int)
    assert opser.core.is_class(bool)
    assert not opser.core.is_class(GenericClass[int])
    assert not opser.core.is_class(t.List[int])
    assert not opser.core.is_class(t.List)


def test_is_generic() -> None:
    assert not opser.core.is_generic(Simple)
    assert not opser.core.is_generic(Parent)
    assert not opser.core.is_generic(GenericClass)
    assert not opser.core.is_generic(t.List)
    assert opser.core.is_generic(GenericClass[int])
    assert opser.core.is_generic(t.List[int])


def test_unwrap_generic() -> None:
    assert opser.core.unwrap_generic(t.List[int]) == (list, int)
    assert opser.core.unwrap_generic(t.Dict[int, str]) == (dict, int, str)
    assert opser.core.unwrap_generic(t.Dict[str, int]) == (dict, str, int)
    assert opser.core.unwrap_generic(GenericClass[int]) == (GenericClass, int)


def test_is_optional() -> None:
    assert opser.core.is_optional(t.Optional[int])
    assert opser.core.is_optional(t.Union[float, None])
    assert not opser.core.is_optional(t.Union[None])
    assert not opser.core.is_optional(t.List[int])


def test_optional_args() -> None:
    assert opser.core.optional_args(t.Optional[int]) == (int,)
    assert opser.core.optional_args(t.Optional[t.Union[int, float]]) == (int, float)
    assert opser.core.optional_args(t.Optional[t.Union[float, int]]) == (int, float)
    assert opser.core.optional_args(t.Union[float, int, str, None]) == (float, int, str)
    assert opser.core.optional_args(Simple) == ()
    assert opser.core.optional_args(Parent) == ()


def test_registering_persistors_is_idempotent() -> None:
    original_registry_size = RegistryPersistor.registry_size()

    # already registered
    opser.register_json_presentable(a121.SessionConfig)

    assert original_registry_size == RegistryPersistor.registry_size()
