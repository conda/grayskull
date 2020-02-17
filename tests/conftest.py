import os

from pytest import fixture


@fixture
def data_dir() -> str:
    return os.path.join(os.path.dirname(__file__), "data")
