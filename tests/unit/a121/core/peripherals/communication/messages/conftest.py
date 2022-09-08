# Copyright (c) Acconeer AB, 2022
# All rights reserved

import unittest.mock

import pytest


@pytest.fixture
def mock_client():
    mock = unittest.mock.Mock()
    mock._result_queue = []
    mock._sensor_infos = {}
    mock._system_info = None
    return mock
