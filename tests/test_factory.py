import pytest
from pip._internal.models.index import PyPI

from grayskull.base.base_recipe import Grayskull
from grayskull.base.factory import GrayskullFactory


@pytest.mark.parametrize(
    "repo_type, pkg_name, version, obj_type", [("pypi", "pytest", "5.3.2", PyPI)]
)
def test_factory(repo_type, pkg_name, version, obj_type):
    assert isinstance(
        GrayskullFactory.create_recipe(repo_type, pkg_name, version),
        (Grayskull, obj_type),
    )
