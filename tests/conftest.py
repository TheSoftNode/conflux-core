import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402


@pytest.fixture(autouse=True)
def clean_state():
    server.ROOMS.clear()
    server.CREATE_LOG.clear()
    yield
    server.ROOMS.clear()
    server.CREATE_LOG.clear()
