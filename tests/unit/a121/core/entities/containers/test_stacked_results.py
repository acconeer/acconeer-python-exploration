import numpy as np
import pytest

from acconeer.exptool.a121._core.entities import (
    INT_16_COMPLEX,
    Metadata,
    Result,
    ResultContext,
    StackedResults,
)


class TestAnEmptyStackedResults:
    @pytest.fixture
    def stacked_results(self):
        return StackedResults(
            calibration_needed=np.array([]),
            data_saturated=np.array([]),
            frame_delayed=np.array([]),
            temperature=np.array([]),
            tick=np.array([]),
            frame=np.array([[[]]], dtype=INT_16_COMPLEX),
            context=ResultContext(
                ticks_per_second=1,
                metadata=Metadata(
                    frame_data_length=0,
                    sweep_data_length=0,
                    subsweep_data_offset=np.array([0]),
                    subsweep_data_length=np.array([0]),
                    calibration_temperature=0,
                    tick_period=0,
                    base_step_length_m=0,
                    max_sweep_rate=0,
                ),
            ),
        )

    def test_has_a_frame_with_3_dimensions(self, stacked_results):
        assert stacked_results.frame.ndim == 3

    def test_has_subframes_3_dimensions(self, stacked_results):
        for subframe in stacked_results.subframes:
            assert subframe.ndim == 3

    def test_should_return_an_empty_frame(self, stacked_results):
        assert stacked_results.frame.size == 0

    def test_should_return_empty_subframes(self, stacked_results):
        for subframe in stacked_results.subframes:
            assert subframe.size == 0

    def test_is_not_indexable(self, stacked_results):
        with pytest.raises(IndexError):
            _ = stacked_results[0]


class TestStackedResultWithASingleFrame:
    @pytest.fixture
    def context(self):
        return ResultContext(
            ticks_per_second=1,
            metadata=Metadata(
                frame_data_length=2,
                sweep_data_length=2,
                subsweep_data_offset=np.array([0, 1]),
                subsweep_data_length=np.array([1, 1]),
                calibration_temperature=0,
                tick_period=0,
                base_step_length_m=0,
                max_sweep_rate=0,
            ),
        )

    @pytest.fixture
    def result(self, context):
        return Result(
            calibration_needed=False,
            data_saturated=False,
            frame_delayed=False,
            temperature=23,
            tick=0,
            frame=np.array([[(1, 1), (2, 2)]], dtype=INT_16_COMPLEX),
            context=context,
        )

    @pytest.fixture
    def stacked_results(self, context):
        return StackedResults(
            calibration_needed=np.array([False]),
            data_saturated=np.array([False]),
            frame_delayed=np.array([False]),
            temperature=np.array([23]),
            tick=np.array([0]),
            frame=np.array([[[(1, 1), (2, 2)]]], dtype=INT_16_COMPLEX),
            context=context,
        )

    def test_has_a_frame_with_3_dimensions(self, stacked_results):
        assert stacked_results.frame.ndim == 3

    def test_has_subframes_3_dimensions(self, stacked_results):
        for subframe in stacked_results.subframes:
            assert subframe.ndim == 3

    def test_has_correct_subsweeps(self, stacked_results):
        subframe1, subframe2 = stacked_results.subframes

        expected_subframe1 = np.array(
            [
                [[1 + 1j]],
            ]
        )
        expected_subframe2 = np.array(
            [
                [[2 + 2j]],
            ]
        )

        np.testing.assert_array_equal(expected_subframe1, subframe1)
        np.testing.assert_array_equal(expected_subframe2, subframe2)

    def test_frame_is_converted_to_complex_type(self, stacked_results):
        expected = np.array(
            [
                [[1 + 1j, 2 + 2j]],
            ],
        )
        np.testing.assert_array_equal(stacked_results.frame, expected)

    def test_is_indexable_and_returns_a_result(self, stacked_results, result):
        assert stacked_results[0] == result

    def test_reports_the_number_of_results_in_len(self, stacked_results):
        assert len(stacked_results) == 1


class TestStackedResultWithMultipleFrames:
    @pytest.fixture
    def context(self):
        return ResultContext(
            ticks_per_second=1,
            metadata=Metadata(
                frame_data_length=2,
                sweep_data_length=2,
                subsweep_data_offset=np.array([0, 1]),
                subsweep_data_length=np.array([1, 1]),
                calibration_temperature=0,
                tick_period=0,
                base_step_length_m=0,
                max_sweep_rate=0,
            ),
        )

    @pytest.fixture
    def result1(self, context):
        return Result(
            calibration_needed=False,
            data_saturated=False,
            frame_delayed=False,
            temperature=23,
            tick=0,
            frame=np.array([[(1, 1), (2, 2)]], dtype=INT_16_COMPLEX),
            context=context,
        )

    @pytest.fixture
    def result2(self, context):
        return Result(
            calibration_needed=False,
            data_saturated=False,
            frame_delayed=False,
            temperature=23,
            tick=1,
            frame=np.array([[(3, 3), (4, 4)]], dtype=INT_16_COMPLEX),
            context=context,
        )

    @pytest.fixture
    def stacked_results(self, context):
        return StackedResults(
            calibration_needed=np.array([False] * 2),
            data_saturated=np.array([False] * 2),
            frame_delayed=np.array([False] * 2),
            temperature=np.array([23] * 2),
            tick=np.array([0, 1]),
            frame=np.array(
                [
                    [
                        [(1, 1), (2, 2)],
                    ],
                    [
                        [(3, 3), (4, 4)],
                    ],
                ],
                dtype=INT_16_COMPLEX,
            ),
            context=context,
        )

    def test_has_a_frame_with_3_dimensions(self, stacked_results):
        assert stacked_results.frame.ndim == 3

    def test_has_subframes_3_dimensions(self, stacked_results):
        for subframe in stacked_results.subframes:
            assert subframe.ndim == 3

    def test_frame_is_converted_correctly(self, stacked_results):
        expected = np.array(
            [
                [[1 + 1j, 2 + 2j]],
                [[3 + 3j, 4 + 4j]],
            ],
        )

        np.testing.assert_array_equal(stacked_results.frame, expected)

    def test_has_correct_subsweeps(self, stacked_results):
        subframe1, subframe2 = stacked_results.subframes

        expected_subframe1 = np.array(
            [
                [[1 + 1j]],
                [[3 + 3j]],
            ]
        )
        expected_subframe2 = np.array(
            [
                [[2 + 2j]],
                [[4 + 4j]],
            ]
        )
        np.testing.assert_array_equal(expected_subframe1, subframe1)
        np.testing.assert_array_equal(expected_subframe2, subframe2)

    def test_is_indexable_and_returns_correct_result(self, stacked_results, result1, result2):
        assert stacked_results[0] == result1
        assert stacked_results[1] == result2

    def test_reports_the_number_of_results_in_len(self, stacked_results):
        assert len(stacked_results) == 2
