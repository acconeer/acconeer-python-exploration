# Copyright (c) Acconeer AB, 2022
# All rights reserved

import unittest.mock

import pytest


@pytest.fixture
def mock_client() -> unittest.mock.Mock:
    mock = unittest.mock.Mock()
    mock._result_queue = []
    mock._sensor_infos = {}
    mock._system_info = None
    return mock
