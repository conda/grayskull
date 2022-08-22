from grayskull.__main__ import create_python_recipe
from grayskull.strategy.py_base import (
    clean_deps_for_conda_forge,
    ensure_pep440,
    update_requirements_with_pin,
)
from grayskull.utils import PyVer


def test_ensure_pep440():
    assert ensure_pep440("pytest ~=5.3.2") == "pytest >=5.3.2,<5.4.dev0"


def test_pep440_recipe():
    recipe = create_python_recipe("codalab=0.5.26", is_strict_cf=False)[0]
    assert recipe["requirements"]["host"] == ["python >=3.6", "pip"]


def test_pep440_in_recipe_pypi():
    recipe = create_python_recipe("kedro=0.17.6", is_strict_cf=False)[0]
    assert sorted(recipe["requirements"]["run"])[0] == "anyconfig >=0.10.0,<0.11.dev0"


def test_update_requirements_with_pin_mixed_numpy_pin_compatible():
    requirements = {
        "build": ["<{ compiler('c') }}"],
        "host": ["cython", "numpy", "pip", "python"],
        "run": ["numpy >=1.19.1,<2.0.0", "pyparsing >=2.4.7, <3.0.0", "python"],
    }
    update_requirements_with_pin(requirements)
    assert "<{ pin_compatible('numpy') }}" in requirements["run"]
    assert "numpy" not in requirements["run"]


def test_ensure_pep440_stripping_empty_spaces():
    assert (
        ensure_pep440("dulwich >=0.19.3  # [py>=35]") == "dulwich >=0.19.3  # [py>=35]"
    )


def test_clean_deps_for_conda_forge_remove_py_selector():
    assert clean_deps_for_conda_forge(
        ["dulwich >=0.19.3  # [py>=35]"], PyVer(3, 6)
    ) == ["dulwich >=0.19.3"]
