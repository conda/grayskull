import pytest

from grayskull.base.base_recipe import AbstractRecipeModel
from grayskull.base.factory import GrayskullFactory
from grayskull.pypi import PyPi


@pytest.mark.parametrize(
    "repo_type, pkg_name, version, obj_type", [("pypi", "requests", "2.22.0", PyPi)]
)
def test_factory(repo_type, pkg_name, version, obj_type, monkeypatch):
    monkeypatch.setattr(PyPi, "__init__", lambda x, y, z: None)
    assert isinstance(
        GrayskullFactory.create_recipe(repo_type, pkg_name, version),
        (AbstractRecipeModel, obj_type),
    )
