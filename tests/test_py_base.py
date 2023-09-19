from pathlib import Path

from grayskull.config import Configuration
from grayskull.main import create_python_recipe
from grayskull.strategy.py_base import (
    clean_deps_for_conda_forge,
    ensure_pep440,
    generic_py_ver_to,
    get_sdist_metadata,
    merge_deps_toml_setup,
    split_deps,
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


def test_python_requires_upper_bound():
    py_ver = generic_py_ver_to(
        {"requires_python": ">=3.7,<=3.10"},
        Configuration(name="algviz", is_strict_cf=False),
    )
    assert py_ver == ">=3.7,<3.11"


def test_merge_deps_toml_setup():
    assert merge_deps_toml_setup(["abc>1.0.0", "gh"], ["abc >1.0.0", "def"]) == [
        "abc >1.0.0",
        "def",
        "gh",
    ]


def test_get_sdist_metadata_toml_files_windrose():
    windrose_path = Path(__file__).parent / "data" / "pkgs" / "windrose-1.8.1.tar"

    sdist_metadata = get_sdist_metadata(
        str(windrose_path),
        Configuration(
            name="windrose",
            version="1.8.1",
            from_local_sdist=True,
            local_sdist=str(windrose_path),
        ),
    )
    assert sdist_metadata["setup_requires"] == [
        "setuptools>=41.2",
        "setuptools_scm",
        "wheel",
    ]


def test_get_sdist_metadata_toml_files_BLACK():
    smithy_path = Path(__file__).parent / "data" / "pkgs" / "black-22.12.0.zip"
    sdist_metadata = get_sdist_metadata(
        str(smithy_path),
        Configuration(
            name="black",
            version="22.12.0",
            from_local_sdist=True,
            local_sdist=str(smithy_path),
        ),
    )
    assert sdist_metadata["license"] == "MIT"
    assert sdist_metadata["entry_points"]["console_scripts"] == [
        "black = black:patched_main",
        "blackd = blackd:patched_main [d]",
    ]
    assert sdist_metadata["setup_requires"] == [
        "hatchling>=1.8.0",
        "hatch-vcs",
        "hatch-fancy-pypi-readme",
        "python >=3.7",
    ]
    assert sdist_metadata["install_requires"] == [
        "click>=8.0.0",
        "mypy_extensions>=0.4.3",
        "pathspec>=0.9.0",
        "platformdirs>=2",
        "tomli>=1.1.0; python_full_version < '3.11.0a7'",
        "typed-ast>=1.4.2; python_version < '3.8' and implementation_name == 'cpython'",
        "typing_extensions>=3.10.0.0; python_version < '3.10'",
        "python >=3.7",
    ]


def test_split_deps_without_comma():
    assert split_deps(">=1.8.0<3.0.0,!=2.0.1") == [">=1.8.0", "<3.0.0", "!=2.0.1"]


def test_split_deps():
    assert split_deps(">=1.8.0,<3.0.0,!=2.0.1") == [">=1.8.0", "<3.0.0", "!=2.0.1"]


def test_split_deps_space():
    assert split_deps(">=1.8.0 <3.0.0 !=2.0.1") == [">=1.8.0", "<3.0.0", "!=2.0.1"]
