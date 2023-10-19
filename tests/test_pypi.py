import hashlib
import json
import os
import sys
from unittest.mock import patch

import pytest
from colorama import Fore, Style
from souschef.recipe import Recipe

from grayskull.base.factory import GrayskullFactory
from grayskull.base.pkg_info import normalize_pkg_name
from grayskull.cli import CLIConfig
from grayskull.cli.parser import parse_pkg_name_version
from grayskull.config import Configuration
from grayskull.main import create_python_recipe
from grayskull.strategy.py_base import (
    clean_deps_for_conda_forge,
    generic_py_ver_to,
    get_compilers,
    get_entry_points_from_sdist,
    get_extra_from_requires_dist,
    get_name_version_from_requires_dist,
    get_sdist_metadata,
    get_setup_cfg,
    get_test_entry_points,
    get_test_imports,
    parse_extra_metadata_to_selector,
    py_version_to_limit_python,
    py_version_to_selector,
    update_requirements_with_pin,
)
from grayskull.strategy.pypi import (
    PypiStrategy,
    check_noarch_python_for_new_deps,
    compose_test_section,
    extract_optional_requirements,
    extract_requirements,
    get_all_selectors_pypi,
    get_pypi_metadata,
    get_sha256_from_pypi_metadata,
    get_url_filename,
    merge_pypi_sdist_metadata,
    normalize_requirements_list,
    remove_all_inner_nones,
    remove_selectors_pkgs_if_needed,
    sort_reqs,
    update_recipe,
)
from grayskull.utils import PyVer, format_dependencies, generate_recipe


@pytest.fixture
def pypi_metadata():
    path_metadata = os.path.join(
        os.path.dirname(__file__), "data", "pypi_pytest_metadata.json"
    )
    with open(path_metadata) as f:
        return json.load(f)


@pytest.fixture
def freeze_py_cf_supported():
    return [
        PyVer(3, 6),
        PyVer(3, 7),
        PyVer(3, 8),
        PyVer(3, 9),
        PyVer(3, 10),
        PyVer(3, 11),
    ]


@pytest.fixture
def recipe_config():
    config = Configuration(
        name="pytest",
        py_cf_supported=[
            PyVer(3, 6),
            PyVer(3, 7),
            PyVer(3, 8),
            PyVer(3, 9),
            PyVer(3, 10),
            PyVer(3, 11),
            PyVer(3, 12),
        ],
        supported_py=[
            PyVer(2, 7),
            PyVer(3, 6),
            PyVer(3, 7),
            PyVer(3, 8),
            PyVer(3, 9),
            PyVer(3, 10),
            PyVer(3, 11),
        ],
    )
    recipe = Recipe(name="pytest")
    return recipe, config


@pytest.fixture
def pypi_metadata_with_extras():
    path_metadata = os.path.join(
        os.path.dirname(__file__), "data", "pypi_dask_metadata.json"
    )
    with open(path_metadata) as f:
        return json.load(f)


def test_extract_pypi_requirements(pypi_metadata, recipe_config):
    recipe, config = recipe_config
    pypi_metadata["info"]["setup_requires"] = ["tomli >1.0.0 ; python_version >=3.11"]
    pypi_reqs = extract_requirements(pypi_metadata["info"], config, recipe)
    assert sorted(pypi_reqs["host"]) == sorted(
        ["python", "pip", "tomli >1.0.0  # [py>=311]"]
    )
    assert sorted(pypi_reqs["run"]) == sorted(
        [
            "python",
            "py >=1.5.0",
            "packaging",
            "attrs >=17.4.0",
            "more-itertools >=4.0.0",
            "pluggy <1.0,>=0.12",
            "wcwidth",
            "pathlib2 >=2.2.0  # [py<36]",
            "importlib-metadata >=0.12  # [py<38]",
            "atomicwrites >=1.0  # [win]",
            "colorama  # [win]",
        ]
    )


def test_get_pypi_metadata(pypi_metadata):
    recipe = Recipe(name="pytest")
    config = Configuration(name="pytest", version="5.3.1", is_strict_cf=True)
    metadata = get_pypi_metadata(config)
    PypiStrategy.fetch_data(recipe, config)
    assert metadata["name"] == "pytest"
    assert metadata["version"] == "5.3.1"
    assert "pathlib2 >=2.2.0  # [py<36]" not in recipe["requirements"]["run"]


def test_get_name_version_from_requires_dist():
    assert get_name_version_from_requires_dist("py (>=1.5.0)") == (
        "py",
        ">=1.5.0",
    )


def test_get_extra_from_requires_dist():
    assert get_extra_from_requires_dist(' python_version < "3.6"') == [
        (
            "",
            "python_version",
            "<",
            "3.6",
            "",
            "",
        )
    ]
    assert get_extra_from_requires_dist(
        " python_version < \"3.6\" ; extra =='test'"
    ) == [
        ("", "python_version", "<", "3.6", "", ""),
        ("", "extra", "==", "test", "", ""),
    ]
    assert get_extra_from_requires_dist(
        ' (sys_platform =="win32" and python_version =="2.7") and extra =="socks"'
    ) == [
        ("(", "sys_platform", "==", "win32", "", "and"),
        ("", "python_version", "==", "2.7", ")", "and"),
        ("", "extra", "==", "socks", "", ""),
    ]


@pytest.fixture(scope="module")
def dask_sdist_metadata():
    config = Configuration(name="dask")
    return get_sdist_metadata(
        "https://pypi.io/packages/source/d/dask/dask-2022.6.1.tar.gz",
        config,
    )


def test_get_extra_requirements(dask_sdist_metadata):
    received = {
        extra: set(req_lst)
        for extra, req_lst in dask_sdist_metadata["extras_require"].items()
    }
    expected = {
        "array": {"numpy >= 1.18"},
        "bag": set(),
        "dataframe": {"pandas >= 1.0", "numpy >= 1.18"},
        "distributed": {"distributed == 2022.6.1"},
        "diagnostics": {"bokeh >= 2.4.2", "jinja2"},
        "delayed": set(),
        "complete": {
            "bokeh >= 2.4.2",
            "numpy >= 1.18",
            "distributed == 2022.6.1",
            "pandas >= 1.0",
            "jinja2",
        },
        "test": {"pytest-xdist", "pytest-rerunfailures", "pre-commit", "pytest"},
    }
    assert received == expected


def test_extract_optional_requirements(dask_sdist_metadata):
    config = Configuration(name="dask")

    received = extract_optional_requirements(dask_sdist_metadata, config)
    assert not received

    all_optional_reqs = {
        "array": {"numpy >=1.18"},
        "complete": {
            "distributed ==2022.6.1",
            "pandas >=1.0",
            "numpy >=1.18",
            "bokeh >=2.4.2",
            "jinja2",
        },
        "dataframe": {"numpy >=1.18", "pandas >=1.0"},
        "diagnostics": {"bokeh >=2.4.2", "jinja2"},
        "distributed": {"distributed ==2022.6.1"},
        "test": {"pytest-xdist", "pre-commit", "pytest-rerunfailures", "pytest"},
    }

    config.extras_require_all = True
    received = extract_optional_requirements(dask_sdist_metadata, config)
    received = {k: set(v) for k, v in received.items()}
    expected = {k: set(v) for k, v in all_optional_reqs.items()}
    assert received == expected

    config.extras_require_all = True
    config.extras_require_include = None
    config.extras_require_exclude = ["complete"]
    received = extract_optional_requirements(dask_sdist_metadata, config)
    received = {k: set(v) for k, v in received.items()}
    expected = {k: set(v) for k, v in all_optional_reqs.items() if k != "complete"}
    assert received == expected

    config.extras_require_all = False
    config.extras_require_include = ["complete"]
    config.extras_require_exclude = None
    received = extract_optional_requirements(dask_sdist_metadata, config)
    received = {k: set(v) for k, v in received.items()}
    expected = {k: set(v) for k, v in all_optional_reqs.items() if k == "complete"}
    assert received == expected

    config.extras_require_all = True
    config.extras_require_include = ["complete"]
    config.extras_require_exclude = None
    received = extract_optional_requirements(dask_sdist_metadata, config)
    received = {k: set(v) for k, v in received.items()}
    expected = {k: set(v) for k, v in all_optional_reqs.items()}
    assert received == expected

    config.extras_require_all = True
    config.extras_require_include = None
    config.extras_require_exclude = ["complete", "test"]
    received = extract_optional_requirements(dask_sdist_metadata, config)
    received = {k: set(v) for k, v in received.items()}
    expected = {
        k: set(v) for k, v in all_optional_reqs.items() if k not in ("complete", "test")
    }
    assert received == expected

    config.extras_require_all = True
    config.extras_require_include = None
    config.extras_require_exclude = ["complete", "test"]
    config.extras_require_test = "test"
    received = extract_optional_requirements(dask_sdist_metadata, config)
    received = {k: set(v) for k, v in received.items()}
    expected = {k: set(v) for k, v in all_optional_reqs.items() if k != "complete"}
    assert received == expected


def test_compose_test_section_with_console_scripts():
    config = Configuration(name="pytest", version="7.1.2")
    metadata1 = get_pypi_metadata(config)
    metadata2 = get_sdist_metadata(
        "https://pypi.io/packages/source/p/pytest/pytest-7.1.2.tar.gz", config
    )
    metadata = merge_pypi_sdist_metadata(metadata1, metadata2, config)
    test_requirements = []
    test_section = compose_test_section(metadata, test_requirements)
    test_section = {k: set(v) for k, v in test_section.items()}
    expected = {
        "imports": {"pytest"},
        "commands": {"pip check", "py.test --help", "pytest --help"},
        "requires": {"pip"},
    }
    assert test_section == expected


def test_compose_test_section_with_requirements(dask_sdist_metadata):
    config = Configuration(name="dask", version="2022.7.1")
    metadata = get_pypi_metadata(config)
    test_requirements = dask_sdist_metadata["extras_require"]["test"]
    test_section = compose_test_section(metadata, test_requirements)
    test_section = {k: set(v) for k, v in test_section.items()}
    expected = {
        "imports": {"dask"},
        "commands": {"pip check", "pytest --pyargs dask"},
        "requires": {
            "pip",
            "pytest",
            "pytest-xdist",
            "pytest-rerunfailures",
            "pre-commit",
        },
    }
    assert test_section == expected


def test_get_include_extra_requirements():
    base_requirements = [
        "cloudpickle >=1.1.1",
        "fsspec >=0.6.0",
        "packaging >=20.0",
        "partd >=0.3.10",
        "python >=3.8",
        "pyyaml >=5.3.1",
        "toolz >=0.8.2",
    ]
    host_requirements = ["python >=3.8", "pip"]

    extras = {}
    extras["array"] = ["numpy >=1.18"]
    extras["distributed"] = ["distributed ==2022.6.1"]
    extras["diagnostics"] = ["bokeh >=2.4.2", "jinja2"]
    extras["dataframe"] = ["numpy >=1.18", "pandas >=1.0"]
    extras["test"] = ["pytest-xdist", "pytest", "pytest-rerunfailures", "pre-commit"]
    extras["complete"] = [
        "distributed ==2022.6.1",
        "jinja2",
        "numpy >=1.18",
        "bokeh >=2.4.2",
        "pandas >=1.0",
    ]

    def set_of_strings(sequence):
        return set(map(str, sequence))

    # extras are not used
    config = Configuration(name="dask", version="2022.6.1")
    recipe = GrayskullFactory.create_recipe("pypi", config)
    assert recipe["package"]["name"] == "<{ name|lower }}"
    assert set(recipe["outputs"]) == set()
    assert set(recipe["requirements"]["host"]) == set(host_requirements)
    assert set(recipe["requirements"]["run"]) == set(base_requirements)
    assert set(recipe["test"]["requires"]) == {"pip"}

    # all extras are included in the requirements
    config = Configuration(name="dask", version="2022.6.1", extras_require_all=True)
    recipe = GrayskullFactory.create_recipe("pypi", config)
    assert recipe["package"]["name"] == "<{ name|lower }}"
    assert set(recipe["outputs"]) == set()

    expected = list(base_requirements)
    for name, req_lst in extras.items():
        if name != "complete":
            expected.append(f"Extra: {name}")
            expected.extend(req_lst)
    assert set(recipe["requirements"]["host"]) == set(host_requirements)
    assert set_of_strings(recipe["requirements"]["run"]) == set(expected)
    assert set_of_strings(recipe["test"]["requires"]) == {"pip"}

    # all extras are included in the requirements except for the
    # test requirements which are in the test section
    config = Configuration(
        name="dask",
        version="2022.6.1",
        extras_require_all=True,
        extras_require_test="test",
    )
    recipe = GrayskullFactory.create_recipe("pypi", config)
    assert recipe["package"]["name"] == "<{ name|lower }}"
    assert set(recipe["outputs"]) == set()

    expected = list(base_requirements)
    for name, req_lst in extras.items():
        if name not in ("test", "complete"):
            expected.append(f"Extra: {name}")
            expected.extend(req_lst)
    assert set(recipe["requirements"]["host"]) == set(host_requirements)
    assert set_of_strings(recipe["requirements"]["run"]) == set(expected)
    assert set_of_strings(recipe["test"]["requires"]) == {"pip", *extras["test"]}

    # only "array" is included in the requirements
    config = Configuration(
        name="dask", version="2022.6.1", extras_require_include=("array",)
    )
    recipe = GrayskullFactory.create_recipe("pypi", config)
    assert recipe["package"]["name"] == "<{ name|lower }}"
    assert set(recipe["outputs"]) == set()
    assert set(recipe["requirements"]["host"]) == set(host_requirements)
    assert set_of_strings(recipe["requirements"]["run"]) == {
        *base_requirements,
        "Extra: array",
        *extras["array"],
    }
    assert set_of_strings(recipe["test"]["requires"]) == {"pip"}

    # only "test" is included but in the test section
    config = Configuration(
        name="dask",
        version="2022.6.1",
        extras_require_all=True,
        extras_require_exclude=set(extras) - {"test"},
        extras_require_test="test",
    )
    recipe = GrayskullFactory.create_recipe("pypi", config)
    assert recipe["package"]["name"] == "<{ name|lower }}"
    assert set(recipe["outputs"]) == set()
    assert set(recipe["requirements"]["host"]) == set(host_requirements)
    assert set_of_strings(recipe["requirements"]["run"]) == set(base_requirements)
    assert set_of_strings(recipe["test"]["requires"]) == {"pip", *extras["test"]}

    # only "test" is included in the test section
    config = Configuration(
        name="dask",
        version="2022.6.1",
        extras_require_all=True,
        extras_require_exclude=set(extras) - {"test"},
        extras_require_test="test",
        extras_require_split=True,
    )
    recipe = GrayskullFactory.create_recipe("pypi", config)
    assert recipe["package"]["name"] == "<{ name|lower }}"
    assert set(recipe["outputs"]) == set()
    assert set(recipe["requirements"]["host"]) == set(host_requirements)
    assert set_of_strings(recipe["requirements"]["run"]) == set(base_requirements)
    assert set_of_strings(recipe["test"]["requires"]) == {"pip", *extras["test"]}

    # all extras have their own output except for the
    # test requirements which are in the test section
    config = Configuration(
        name="dask",
        version="2022.6.1",
        extras_require_all=True,
        extras_require_test="test",
        extras_require_split=True,
    )
    recipe = GrayskullFactory.create_recipe("pypi", config)
    assert recipe["package"]["name"] == "<{ name|lower }}"
    assert set(recipe["requirements"]["host"]) == set(host_requirements)
    assert set(recipe["requirements"]["run"]) == set(base_requirements)
    assert len(recipe["outputs"]) == 6

    expected = {}
    for name, req_lst in extras.items():
        if name != "test":
            expected[f"dask-{name}"] = {
                "{{ pin_subpackage('dask', exact=True) }}",
                "python >=3.8",
                *req_lst,
            }
    found = {}
    for output in recipe["outputs"]:
        if output["name"] == "dask":
            assert "requirements" not in output
        else:
            assert set(output["requirements"]["host"]) == set(host_requirements)
            found[output["name"]] = set_of_strings(output["requirements"]["run"])
    assert found == expected

    expected = {"pip", *extras["test"]}
    assert set_of_strings(recipe["test"]["requires"]) == expected
    for output in recipe["outputs"]:
        if output["name"] == "dask":
            assert "test" not in output
        else:
            assert set_of_strings(output["test"]["requires"]) == expected

    expected = {"noarch": "python"}
    for output in recipe["outputs"]:
        if output["name"] == "dask":
            assert "build" not in output
        else:
            assert output["build"] == expected


def test_normalize_requirements_list():
    config = Configuration(name="pytest")
    requirements = ["pytest ~=5.3.2", "pyqt5"]
    requirements = set(normalize_requirements_list(requirements, config))
    expected = {"pytest >=5.3.2,<5.4.dev0", "pyqt"}
    assert requirements == expected


def test_get_all_selectors_pypi(recipe_config):
    _, config = recipe_config
    config.version = "5.3.1"
    assert get_all_selectors_pypi(
        [
            ("(", "sys_platform", "==", "win32", "", "and"),
            ("", "python_version", "==", "2.7", ")", "and"),
            ("", "extra", "==", "socks", "", ""),
        ],
        config,
    ) == ["(", "win", "and", "py==27", ")"]


def test_get_selector():
    assert parse_extra_metadata_to_selector("extra", "==", "win32") == ""
    assert parse_extra_metadata_to_selector("sys_platform", "==", "win32") == "win"
    assert parse_extra_metadata_to_selector("python_version", "<", "3.6") == "py<36"


@pytest.mark.parametrize(
    "requires_python, exp_selector, ex_cf",
    [
        (">=3.5", "2k", "<36"),
        (">=3.6", "2k", None),
        (">=3.7", "<37", "<37"),
        ("<=3.7", ">=38", ">=38"),
        ("<=3.7.1", ">=38", ">=38"),
        ("<3.7", ">=37", ">=37"),
        (">2.7, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*, !=3.4.*", "<36", "<36"),
        (">=2.7, !=3.6.*", "==36", "<37"),
        (">3.7", "<38", "<38"),
        (">2.7", "2k", "<36"),
        ("<3", "3k", "skip"),
        ("!=3.7", "==37", "==37"),
        ("~=3.7", "<37", "<37"),
    ],
)
def test_py_version_to_selector(requires_python, exp_selector, ex_cf, recipe_config):
    config = recipe_config[1]
    metadata = {"requires_python": requires_python}
    assert py_version_to_selector(metadata, config) == f"# [py{exp_selector}]"

    if ex_cf != "skip":
        expected = f"# [py{ex_cf}]" if ex_cf else None
        config.is_strict_cf = True
        result = py_version_to_selector(metadata, config)
        if isinstance(expected, str):
            assert expected == result
        else:
            assert expected is result


@pytest.mark.parametrize(
    "requires_python, exp_limit, ex_cf",
    [
        (">=3.5", ">=3.5", ">=3.6"),
        (">=3.6", ">=3.6", ">=3.6"),
        (">=3.7", ">=3.7", ">=3.7"),
        ("<=3.7", "<3.8", "<3.8"),
        ("<=3.7.1", "<3.8", "<3.8"),
        ("<3.7", "<3.7", "<3.7"),
        (">2.7, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*, !=3.4.*", ">=3.6", ">=3.6"),
        (">=2.7, !=3.6.*", "!=3.6", ">=3.7"),
        (">3.7", ">=3.8", ">=3.8"),
        (">2.7", ">=3.6", ">=3.6"),
        ("<3", "<3.0", "skip"),
        ("!=3.7", "!=3.7", "!=3.7"),
        ("~=3.7", ">=3.7", ">=3.7"),
    ],
)
def test_py_version_to_limit_python(requires_python, exp_limit, ex_cf, recipe_config):
    metadata = {"requires_python": requires_python}
    assert py_version_to_limit_python(metadata, recipe_config[1]) == f"{exp_limit}"

    if ex_cf != "skip":
        config = recipe_config[1]
        config.is_strict_cf = True
        result = py_version_to_limit_python(metadata, config)
        if isinstance(ex_cf, str):
            assert ex_cf == result
        else:
            assert ex_cf is result


def test_get_sha256_from_pypi_metadata():
    metadata = {
        "urls": [
            {"packagetype": "egg", "digests": {"sha256": "23123"}},
            {"packagetype": "sdist", "digests": {"sha256": "1234sha256"}},
        ]
    }
    assert get_sha256_from_pypi_metadata(metadata) == "1234sha256"

    metadata = {
        "urls": [
            {"packagetype": "egg", "digests": {"sha256": "23123"}},
            {"packagetype": "wheel", "digests": {"sha256": "1234sha256"}},
        ]
    }
    with pytest.raises(AttributeError) as err:
        get_sha256_from_pypi_metadata(metadata)
    assert err.match("Hash information for sdist was not found on PyPi metadata.")


@pytest.mark.github
@pytest.mark.parametrize(
    "name", ["hypothesis", "https://github.com/HypothesisWorks/hypothesis"]
)
def test_injection_distutils(name):
    config = Configuration(name="hypothesis")
    data = get_sdist_metadata(
        "https://pypi.io/packages/source/h/hypothesis/hypothesis-5.5.1.tar.gz",
        config,
    )
    assert sorted(data["install_requires"]) == sorted(
        ["attrs>=19.2.0", "sortedcontainers>=2.1.0,<3.0.0"]
    )
    assert data["entry_points"] == {
        "pytest11": ["hypothesispytest = hypothesis.extra.pytestplugin"]
    }
    assert data["version"] == "5.5.1"
    assert data["name"] == "hypothesis"
    assert not data.get("compilers")


def test_injection_distutils_pytest():
    config = Configuration(name="pytest", version="5.3.2")
    data = get_sdist_metadata(
        "https://pypi.io/packages/source/p/pytest/pytest-5.3.2.tar.gz", config
    )
    assert sorted(data["install_requires"]) == sorted(
        [
            "py>=1.5.0",
            "packaging",
            "attrs>=17.4.0",
            "more-itertools>=4.0.0",
            'atomicwrites>=1.0;sys_platform=="win32"',
            'pathlib2>=2.2.0;python_version<"3.6"',
            'colorama;sys_platform=="win32"',
            "pluggy>=0.12,<1.0",
            'importlib-metadata>=0.12;python_version<"3.8"',
            "wcwidth",
        ]
    )
    assert sorted(data["setup_requires"]) == sorted(
        ["setuptools-scm", "setuptools>=40.0", "wheel"]
    )
    assert not data.get("compilers")


def test_injection_distutils_compiler_gsw():
    config = Configuration(name="gsw", version="3.3.1")
    data = get_sdist_metadata(
        "https://pypi.io/packages/source/g/gsw/gsw-3.3.1.tar.gz", config
    )
    assert data.get("compilers") == ["c"]
    assert data["packages"] == ["gsw"]


def test_injection_distutils_setup_reqs_ensure_list():
    pkg_name, pkg_ver = "pyinstaller-hooks-contrib", "2020.7"
    config = Configuration(name=pkg_name, version=pkg_ver)
    data = get_sdist_metadata(
        f"https://pypi.io/packages/source/p/{pkg_name}/{pkg_name}-{pkg_ver}.tar.gz",
        config,
    )
    assert data.get("setup_requires") == ["setuptools >= 30.3.0"]


def test_merge_pypi_sdist_metadata():
    config = Configuration(name="gsw", version="3.3.1")
    pypi_metadata = get_pypi_metadata(config)
    sdist_metadata = get_sdist_metadata(pypi_metadata["sdist_url"], config)
    merged_data = merge_pypi_sdist_metadata(pypi_metadata, sdist_metadata, config)
    assert merged_data["compilers"] == ["c"]
    assert sorted(merged_data["setup_requires"]) == sorted(["numpy"])


def test_update_requirements_with_pin():
    req = {
        "build": ["<{ compiler('c') }}"],
        "host": ["python", "numpy"],
        "run": ["python", "numpy"],
    }
    update_requirements_with_pin(req)
    assert req == {
        "build": ["<{ compiler('c') }}"],
        "host": ["python", "numpy"],
        "run": ["python", "<{ pin_compatible('numpy') }}"],
    }


def test_get_compilers():
    config = Configuration(name="any_package")
    assert get_compilers(["pybind11"], {}, config) == ["cxx"]
    assert get_compilers(["cython"], {}, config) == ["c"]
    assert sorted(get_compilers(["pybind11", "cython"], {}, config)) == sorted(
        ["cxx", "c"]
    )
    assert sorted(get_compilers(["pybind11"], {"compilers": ["c"]}, config)) == sorted(
        ["cxx", "c"]
    )


def test_get_entry_points_from_sdist():
    assert get_entry_points_from_sdist({}) == []
    assert get_entry_points_from_sdist(
        {"entry_points": {"console_scripts": ["console_scripts=entrypoints"]}}
    ) == ["console_scripts=entrypoints"]
    assert get_entry_points_from_sdist(
        {"entry_points": {"gui_scripts": ["gui_scripts=entrypoints"]}}
    ) == ["gui_scripts=entrypoints"]

    assert sorted(
        get_entry_points_from_sdist(
            {
                "entry_points": {
                    "gui_scripts": ["gui_scripts=entrypoints"],
                    "console_scripts": ["console_scripts=entrypoints"],
                }
            }
        )
    ) == sorted(["gui_scripts=entrypoints", "console_scripts=entrypoints"])
    assert sorted(
        get_entry_points_from_sdist(
            {
                "entry_points": {
                    "gui_scripts": None,
                    "console_scripts": "console_scripts=entrypoints",
                }
            }
        )
    ) == sorted(["console_scripts=entrypoints"])
    assert sorted(
        get_entry_points_from_sdist(
            {
                "entry_points": {
                    "gui_scripts": None,
                    "console_scripts": "console_scripts=entrypoints\nfoo=bar.main",
                }
            }
        )
    ) == sorted(["console_scripts=entrypoints", "foo=bar.main"])
    assert sorted(
        get_entry_points_from_sdist(
            {
                "entry_points": {
                    "gui_scripts": "gui_scripts=entrypoints",
                    "console_scripts": None,
                }
            }
        )
    ) == sorted(["gui_scripts=entrypoints"])


def test_build_noarch_skip():
    recipe = create_python_recipe("hypothesis=5.5.2")[0]
    assert recipe["build"]["noarch"] == "python"
    assert "skip" not in recipe["build"]


@pytest.mark.github
def test_build_noarch_skip_github():
    recipe = create_python_recipe(
        "https://github.com/HypothesisWorks/hypothesis", version="5.5.2"
    )[0]
    assert recipe["build"]["noarch"] == "python"
    assert "skip" not in recipe["build"]


def test_run_requirements_sdist():
    config = Configuration(name="botocore", version="1.14.17")
    recipe = GrayskullFactory.create_recipe("pypi", config)
    assert sorted(recipe["requirements"]["run"]) == sorted(
        [
            "docutils >=0.10,<0.16",
            "jmespath >=0.7.1,<1.0.0",
            "python",
            "python-dateutil >=2.1,<3.0.0",
            "urllib3 >=1.20,<1.26",
        ]
    )


def test_format_host_requirements():
    assert sorted(format_dependencies(["setuptools>=40.0", "pkg2"], "pkg1")) == sorted(
        ["setuptools >=40.0", "pkg2"]
    )
    assert sorted(format_dependencies(["setuptools>=40.0", "pkg2"], "pkg2")) == sorted(
        ["setuptools >=40.0"]
    )
    assert sorted(format_dependencies(["setuptools >= 40.0"], "pkg")) == sorted(
        ["setuptools >=40.0"]
    )
    assert sorted(
        format_dependencies(["setuptools_scm [toml] >=3.4.1"], "pkg")
    ) == sorted(["setuptools_scm  >=3.4.1"])


def test_download_pkg_sdist(pkg_pytest):
    with open(pkg_pytest, "rb") as pkg_file:
        content = pkg_file.read()
        pkg_sha256 = hashlib.sha256(content).hexdigest()
    assert (
        pkg_sha256 == "0d5fe9189a148acc3c3eb2ac8e1ac0742cb7618c084f3d228baaec0c254b318d"
    )
    setup_cfg = get_setup_cfg(os.path.dirname(pkg_pytest))
    assert setup_cfg["name"] == "pytest"
    assert setup_cfg["python_requires"] == ">=3.5"
    assert setup_cfg["entry_points"] == {
        "console_scripts": ["pytest=pytest:main", "py.test=pytest:main"]
    }


def test_ciso_recipe():
    recipe = GrayskullFactory.create_recipe(
        "pypi", Configuration(name="ciso", version="0.1.0")
    )
    assert sorted(recipe["requirements"]["host"]) == sorted(
        ["cython", "numpy", "pip", "python"]
    )
    assert sorted(recipe["requirements"]["run"]) == sorted(
        ["cython", "python", "<{ pin_compatible('numpy') }}"]
    )
    assert recipe["test"]["commands"] == ["pip check"]
    assert recipe["test"]["requires"] == ["pip"]
    assert recipe["test"]["imports"] == ["ciso"]


@pytest.mark.serial
@pytest.mark.xfail(
    condition=(sys.platform.startswith("win")),
    reason="Test failing on windows platform",
)
def test_pymc_recipe_fortran():
    recipe = GrayskullFactory.create_recipe(
        "pypi", Configuration(name="pymc", version="2.3.6")
    )
    assert set(recipe["requirements"]["build"]) == {
        "<{ compiler('c') }}",
        "<{ compiler('fortran') }}",
    }
    assert set(recipe["requirements"]["host"]) == {"numpy", "python", "pip"}
    assert set(recipe["requirements"]["run"]) == {
        "<{ pin_compatible('numpy') }}",
        "python",
    }
    assert not recipe["build"]["noarch"]


def test_pytest_recipe_entry_points():
    recipe = create_python_recipe("pytest=5.3.5", is_strict_cf=False)[0]
    assert sorted(recipe["build"]["entry_points"]) == sorted(
        ["pytest=pytest:main", "py.test=pytest:main"]
    )
    assert recipe["about"]["license"] == "MIT"
    assert recipe["about"]["license_file"] == "LICENSE"
    assert "skip" in recipe["build"]
    assert recipe["build"]["skip"].inline_comment == "# [py2k]"
    assert not recipe["build"]["noarch"]
    assert sorted(recipe["test"]["commands"]) == sorted(
        ["py.test --help", "pytest --help", "pip check"]
    )


def test_cythongsl_recipe_build():
    recipe = GrayskullFactory.create_recipe(
        "pypi", Configuration(name="cythongsl", version="0.2.2")
    )

    assert recipe["requirements"]["build"] == ["<{ compiler('c') }}"]
    assert recipe["requirements"]["host"] == ["python", "cython >=0.16", "pip"]
    assert recipe["build"]["noarch"] is None
    assert recipe["build"]["number"] == 0


@pytest.mark.github
@pytest.mark.parametrize("name", ["requests", "https://github.com/psf/requests"])
def test_requests_recipe_extra_deps(capsys, name):
    CLIConfig().stdout = True
    name = parse_pkg_name_version(name)[1]
    config = Configuration(name=name, version="2.22.0")
    recipe = GrayskullFactory.create_recipe("pypi", config)
    captured_stdout = capsys.readouterr()
    assert "win-inet-pton" not in recipe["requirements"]["run"]
    assert recipe["build"]["noarch"]
    assert not recipe["build"]["skip"]
    assert f"{Fore.GREEN}{Style.BRIGHT}python" in captured_stdout.out


def test_zipp_recipe_tags_on_deps():
    config = Configuration(name="zipp", version="3.0.0")
    recipe = GrayskullFactory.create_recipe("pypi", config)
    assert recipe["build"]["noarch"]
    assert sorted(recipe["requirements"]["host"]) == sorted(
        [
            "python >=3.6",
            "pip",
            "setuptools >=42",
            "setuptools-scm >=3.4.1",
            "wheel",
        ]
    )


@pytest.mark.parametrize(
    "requires_python, expected",
    [(">=3.5, <3.8", ">=3.5,<3.8"), (">=3.7", ">=3.7"), ("~=3.6", ">=3.6")],
)
def test_generic_py_ver_to(requires_python, expected):
    config = Configuration(name="abc")
    assert generic_py_ver_to({"requires_python": requires_python}, config) == expected


def test_botocore_recipe_license_name():
    config = Configuration(name="botocore", version="1.15.8")
    recipe = GrayskullFactory.create_recipe("pypi", config)
    assert recipe["about"]["license"] == "Apache-2.0"


def test_ipytest_recipe_license():
    config = Configuration(name="ipytest", version="0.8.0")
    recipe = GrayskullFactory.create_recipe("pypi", config)
    assert recipe["about"]["license"] == "MIT"


def test_get_test_entry_points():
    assert get_test_entry_points("grayskull = grayskull.main:main") == [
        "grayskull --help"
    ]
    assert get_test_entry_points(
        ["pytest = py.test:main", "py.test = py.test:main"]
    ) == ["pytest --help", "py.test --help"]


def test_importlib_metadata_two_setuptools_scm():
    config = Configuration(name="importlib-metadata", version="1.5.0")
    recipe = GrayskullFactory.create_recipe("pypi", config)
    assert "setuptools-scm" in recipe["requirements"]["host"]
    assert "setuptools_scm" not in recipe["requirements"]["host"]
    assert recipe["about"]["license"] == "Apache-2.0"


def test_keyring_host_appearing_twice():
    config = Configuration(name="keyring", version="21.1.1")
    recipe = GrayskullFactory.create_recipe("pypi", config)
    assert "importlib-metadata" in recipe["requirements"]["run"]
    assert "importlib_metadata" not in recipe["requirements"]["run"]


def test_python_requires_setup_py():
    config = Configuration(name="pygments", version="2.6.1")
    recipe = GrayskullFactory.create_recipe("pypi", config)
    assert recipe["build"]["noarch"]
    assert "python >=3.5" in recipe["requirements"]["host"]
    assert "python >=3.5" in recipe["requirements"]["run"]


def test_django_rest_framework_xml_license():
    config = Configuration(name="djangorestframework-xml", version="1.4.0")
    recipe = GrayskullFactory.create_recipe("pypi", config)
    assert recipe["about"]["license_file"] == "LICENSE"
    assert recipe["test"]["imports"][0] == "rest_framework_xml"


def test_get_test_requirements():
    config = Configuration(name="ewokscore", version="0.1.0rc5")
    recipe = GrayskullFactory.create_recipe("pypi", config)
    assert "pytest" not in recipe["test"]["requires"]
    assert "pytest --pyargs ewokscore" not in recipe["test"]["commands"]

    config = Configuration(
        name="ewokscore", version="0.1.0rc5", extras_require_test="wrongoption"
    )
    recipe = GrayskullFactory.create_recipe("pypi", config)
    assert "pytest" not in recipe["test"]["requires"]
    assert "pytest --pyargs ewokscore" not in recipe["test"]["commands"]

    # pytest dependency has no version constraints
    config = Configuration(
        name="ewokscore", version="0.1.0rc5", extras_require_test="test"
    )
    recipe = GrayskullFactory.create_recipe("pypi", config)
    assert "pytest" in recipe["test"]["requires"]
    assert "pytest --pyargs ewokscore" in recipe["test"]["commands"]

    # pytest dependency has version constraints
    config = Configuration(
        name="ewokscore", version="0.1.0rc8 ", extras_require_test="test"
    )
    recipe = GrayskullFactory.create_recipe("pypi", config)
    assert "pytest" in recipe["test"]["requires"]
    assert "pytest --pyargs ewokscore" in recipe["test"]["commands"]


def test_get_test_imports():
    assert get_test_imports({"packages": ["pkg", "pkg.mod1", "pkg.mod2"]}) == ["pkg"]
    assert get_test_imports({"packages": None}, default="pkg-mod") == ["pkg_mod"]
    assert get_test_imports({"packages": "pkg"}, default="pkg-mod") == ["pkg"]


def test_nbdime_license_type():
    config = Configuration(name="nbdime", version="2.0.0")
    recipe = GrayskullFactory.create_recipe("pypi", config)
    assert recipe["about"]["license"] == "BSD-3-Clause"
    assert "setupbase" not in recipe["requirements"]["host"]


def test_normalize_pkg_name():
    assert normalize_pkg_name("mypy-extensions") == "mypy_extensions"
    assert normalize_pkg_name("mypy_extensions") == "mypy_extensions"
    assert normalize_pkg_name("pytest") == "pytest"


def test_mypy_deps_normalization_and_entry_points():
    config = Configuration(name="mypy", version="0.770")
    recipe = GrayskullFactory.create_recipe("pypi", config)
    assert "mypy_extensions >=0.4.3,<0.5.0" in recipe["requirements"]["run"]
    assert "mypy-extensions >=0.4.3,<0.5.0" not in recipe["requirements"]["run"]
    assert "typed-ast >=1.4.0,<1.5.0" in recipe["requirements"]["run"]
    assert "typed_ast <1.5.0,>=1.4.0" not in recipe["requirements"]["run"]
    assert "typing-extensions >=3.7.4" in recipe["requirements"]["run"]
    assert "typing_extensions >=3.7.4" not in recipe["requirements"]["run"]

    assert recipe["build"]["entry_points"] == [
        "mypy=mypy.__main__:console_entry",
        "stubgen=mypy.stubgen:main",
        "stubtest=mypy.stubtest:main",
        "dmypy=mypy.dmypy.client:console_entry",
    ]


@pytest.mark.skipif(
    condition=sys.platform.startswith("win"), reason="Skipping test for win"
)
def test_panel_entry_points(tmpdir):
    config = Configuration(name="panel", version="0.9.1")
    recipe = GrayskullFactory.create_recipe("pypi", config)
    generate_recipe(recipe, config, folder_path=str(tmpdir))
    recipe_path = str(tmpdir / "panel" / "meta.yaml")
    with open(recipe_path, "r") as f:
        content = f.read()
    assert "- panel = panel.cli:main" in content


def test_deps_comments():
    config = Configuration(name="kubernetes_asyncio", version="11.2.0")
    recipe = GrayskullFactory.create_recipe("pypi", config)
    assert sorted(recipe["requirements"]["run"]) == sorted(
        [
            "python",
            "aiohttp >=2.3.10,<4.0.0",
            "certifi >=14.05.14",
            "python-dateutil >=2.5.3",
            "pyyaml >=3.12",
            "setuptools >=21.0.0",
            "six >=1.9.0",
            "urllib3 >=1.24.2",
        ]
    )


@pytest.mark.github
@pytest.mark.parametrize("name", ["respx=0.10.1", "https://github.com/lundberg/respx"])
def test_keep_filename_license(name):
    recipe = create_python_recipe(name)[0]
    assert recipe["about"]["license_file"] == "LICENSE.md"


def test_platform_system_selector():
    assert parse_extra_metadata_to_selector("platform_system", "==", "Windows") == "win"
    assert (
        parse_extra_metadata_to_selector("platform_system", "!=", "Windows")
        == "not win"
    )


def test_tzdata_without_setup_py():
    recipe = create_python_recipe("tzdata=2020.1")[0]
    assert recipe["build"]["noarch"] == "python"
    assert recipe["about"]["home"] == "https://github.com/python/tzdata"


def test_multiples_exit_setup():
    """Bug fix #146"""
    assert create_python_recipe("pyproj=2.6.1")[0]


def test_sequence_inside_another_in_dependencies(freeze_py_cf_supported):
    recipe = create_python_recipe(
        "unittest2=1.1.0",
        is_strict_cf=True,
        py_cf_supported=freeze_py_cf_supported,
    )[0]
    assert sorted(recipe["requirements"]["host"]) == sorted(
        [
            "python >=3.6",
            "argparse",
            "pip",
            "six >=1.4",
            "traceback2",
        ]
    )
    assert sorted(recipe["requirements"]["run"]) == sorted(
        [
            "python >=3.6",
            "argparse",
            "six >=1.4",
            "traceback2",
        ]
    )


def test_recipe_with_just_py_modules():
    recipe = create_python_recipe("python-markdown-math=0.7")[0]
    assert recipe["test"]["imports"] == ["mdx_math"]


def test_recipe_extension():
    recipe = create_python_recipe("azure-identity=1.3.1")[0]
    assert (
        recipe["source"]["url"]
        == "https://pypi.io/packages/source/{{ name[0] }}/{{ name }}/"
        "azure-identity-{{ version }}.zip"
    )


def test_get_url_filename():
    assert get_url_filename({}) == "{{ name }}-{{ version }}.tar.gz"
    assert get_url_filename({}, "default") == "default"
    assert (
        get_url_filename({"urls": [{"packagetype": "nothing"}]})
        == "{{ name }}-{{ version }}.tar.gz"
    )
    assert (
        get_url_filename({"urls": [{"packagetype": "nothing"}]}, "default") == "default"
    )
    assert (
        get_url_filename(
            {
                "info": {"version": "1.2.3"},
                "urls": [{"packagetype": "sdist", "filename": "foo_file-1.2.3.zip"}],
            }
        )
        == "foo_file-{{ version }}.zip"
    )


def test_clean_deps_for_conda_forge():
    assert clean_deps_for_conda_forge(["deps1", "deps2  # [py34]"], PyVer(3, 6)) == [
        "deps1"
    ]
    assert clean_deps_for_conda_forge(["deps1", "deps2  # [py<34]"], PyVer(3, 6)) == [
        "deps1"
    ]
    assert clean_deps_for_conda_forge(["deps1", "deps2  # [py<38]"], PyVer(3, 6)) == [
        "deps1",
        "deps2  # [py<38]",
    ]


def test_empty_entry_points():
    recipe = create_python_recipe("modulegraph=0.18")[0]
    assert recipe["build"]["entry_points"] == [
        "modulegraph = modulegraph.__main__:main"
    ]


def test_noarch_metadata():
    recipe = create_python_recipe("policy_sentry=0.11.16")[0]
    assert recipe["build"]["noarch"] == "python"


def test_arch_metadata():
    recipe = create_python_recipe("remove_dagmc_tags=0.0.5")[0]
    assert "noarch" not in recipe["build"]


def test_entry_points_is_list_of_str():
    """Test to verify that whether console_scripts is a list of strings,
    a multiline string, or a list of empty lists; entry_points is always a list"""
    sdist_metadata = {
        "entry_points": {
            "console_scripts": [
                "ptpython = ptpython.entry_points.run_ptpython:run",
                "ptipython = ptpython.entry_points.run_ptipython:run",
                "ptpython3 = ptpython.entry_points.run_ptpython:run",
                "ptpython3.9 = ptpython.entry_points.run_ptpython:run",
                "ptipython3 = ptpython.entry_points.run_ptipython:run",
                "ptipython3.9 = ptpython.entry_points.run_ptipython:run",
            ]
        },
    }
    assert isinstance(get_entry_points_from_sdist(sdist_metadata), list)
    sdist_metadata = {
        "entry_points": {
            "console_scripts": """
                ptpython = ptpython.entry_points.run_ptpython:run
                ptipython = ptpython.entry_points.run_ptipython:run
                ptpython3 = ptpython.entry_points.run_ptpython:run
                ptpython3.9 = ptpython.entry_points.run_ptpython:run
                ptipython3 = ptpython.entry_points.run_ptipython:run
                ptipython3.9 = ptpython.entry_points.run_ptipython:run
                """
        },
    }
    assert isinstance(get_entry_points_from_sdist(sdist_metadata), list)
    sdist_metadata = {
        "entry_points": {"console_scripts": [[]]},
    }
    assert isinstance(get_entry_points_from_sdist(sdist_metadata), list)


def test_replace_slash_in_imports():
    recipe = create_python_recipe("asgi-lifespan=1.0.1")[0]
    assert ["asgi_lifespan"] == recipe["test"]["imports"]


def test_add_python_min_to_strict_conda_forge(freeze_py_cf_supported):
    recipe = create_python_recipe(
        "dgllife=0.2.8",
        is_strict_cf=True,
        py_cf_supported=freeze_py_cf_supported,
    )[0]
    assert recipe["build"]["noarch"] == "python"
    assert recipe["requirements"]["host"][0] == "python >=3.6"
    assert "python >=3.6" in recipe["requirements"]["run"]


def test_get_test_imports_clean_modules():
    assert get_test_imports(
        {
            "packages": [
                "_pytest",
                "tests",
                "test",
                "_pytest._code",
                "_pytest._io",
                "_pytest.assertion",
                "_pytest.config",
                "_pytest.mark",
                "pytest",
                "pytest.foo",
                "zar",
            ]
        }
    ) == ["pytest", "zar"]
    assert get_test_imports(
        {
            "packages": [
                "_pytest",
                "_pytest._code",
                "_pytest._io",
                "_pytest.assertion",
                "_pytest.config",
                "_pytest.mark",
            ]
        }
    ) == ["_pytest", "_pytest._code"]


def test_create_recipe_from_local_sdist(pkg_pytest):
    recipe = create_python_recipe(pkg_pytest, from_local_sdist=True)[0]
    assert recipe["source"]["url"] == f"file://{pkg_pytest}"
    assert recipe["about"]["home"] == "https://docs.pytest.org/en/latest/"
    assert recipe["about"]["summary"] == "pytest: simple powerful testing with Python"
    assert recipe["about"]["license"] == "MIT"
    assert recipe["about"]["license_file"] == "LICENSE"


@patch("grayskull.strategy.py_base.get_all_toml_info", return_value={})
def test_400_for_python_selector(monkeypatch):
    recipe = create_python_recipe("pyquil", version="3.0.1")[0]
    assert recipe["build"]["skip"].selector == "py>=400 or py2k"


def test_notice_file():
    recipe, _ = create_python_recipe(
        "apache-airflow-providers-databricks", version="3.1.0"
    )
    assert set(recipe["about"]["license_file"]) == {"NOTICE", "LICENSE"}
    assert recipe["about"]["license"] == "Apache-2.0"


def test_notice_file_different_licence():
    with patch(
        "grayskull.license.discovery.get_license_type",
        side_effect=["Apache-2.0", "MIT"],
    ):
        recipe, _ = create_python_recipe(
            "apache-airflow-providers-databricks", version="3.1.0"
        )
    assert set(recipe["about"]["license_file"]) == {"NOTICE", "LICENSE"}
    assert recipe["about"]["license"] in ["MIT AND Apache-2.0", "Apache-2.0 AND MIT"]


def test_console_script_toml_format():
    recipe, _ = create_python_recipe("consolemd", version="0.5.1")
    assert recipe["build"]["entry_points"] == ["consolemd = consolemd.cli:cli"]


def test_section_order():
    recipe, _ = create_python_recipe("requests", version="2.27.1")
    assert (
        "package",
        "source",
        "build",
        "requirements",
        "test",
        "outputs",
        "about",
        "extra",
    ) == tuple(recipe.keys())


def test_no_sdist_pkg_pypi():
    with pytest.raises(
        AttributeError, match="There is no sdist package on pypi for arn"
    ):
        recipe, _ = create_python_recipe("arn", version="0.1.5")


def test_remove_selectors_pkgs_if_needed():
    assert remove_selectors_pkgs_if_needed(
        [
            "import_metadata >1.0  # [py>3]",
            "pywin32  # [win]",
            "requests >=2.0  # [unix]",
        ]
    ) == ["import_metadata >1.0", "pywin32", "requests >=2.0  # [unix]"]


def test_remove_selectors_pkgs_if_needed_with_recipe():
    recipe, _ = create_python_recipe("transformers", is_strict_cf=True, version="4.3.3")
    assert set(recipe["requirements"]["run"]).issubset(
        {
            "dataclasses",
            "filelock",
            "importlib-metadata",
            "numpy >=1.17",
            "packaging",
            "python",
            "regex !=2019.12.17",
            "requests",
            "sacremoses",
            "tokenizers <0.11,>=0.10.1",
            "tokenizers >=0.10.1,<0.11",
            "tqdm >=4.27",
        }
    )


def test_noarch_python_min_constrain(freeze_py_cf_supported):
    recipe, _ = create_python_recipe(
        "humre",
        is_strict_cf=True,
        version="0.1.1",
        py_cf_supported=freeze_py_cf_supported,
    )
    assert recipe["requirements"]["run"] == ["python >=3.6"]


def test_cpp_language_extra():
    recipe, _ = create_python_recipe("xbcausalforest", version="0.1.3")
    assert set(recipe["requirements"]["build"]) == {
        "<{ compiler('cxx') }}",
        "<{ compiler('c') }}",
    }


def test_sort_reqs():
    # There are currently two acceptable sortings. Original ordering or alphabetical.
    # In either sorting, 'python' always comes first.
    original_deps = ["pandas >=1.0", "numpy", "python", "scipy"]
    original_deps_38 = ["pandas >=1.0", "numpy", "python >=3.8", "scipy"]
    sorted_deps_orig = ["python", "pandas >=1.0", "numpy", "scipy"]
    sorted_deps_alpha = ["python", "numpy", "pandas >=1.0", "scipy"]
    sorted_deps_orig_38 = ["python >=3.8", "pandas >=1.0", "numpy", "scipy"]
    sorted_deps_alpha_38 = ["python >=3.8", "numpy", "pandas >=1.0", "scipy"]

    assert sort_reqs(original_deps) in [sorted_deps_orig, sorted_deps_alpha]
    assert sort_reqs(original_deps_38) in [sorted_deps_orig_38, sorted_deps_alpha_38]


@patch("grayskull.strategy.pypi.get_metadata")
def test_metadata_pypi_none_value(mock_get_data):
    mock_get_data.return_value = {
        "package": {"name": "pypylon", "version": "1.2.3"},
        "build": {"test": [None]},
    }
    recipe = Recipe(name="pypylon")
    update_recipe(
        recipe,
        Configuration(name="pypylon", repo_github="https://github.com/basler/pypylon"),
        ("package", "build"),
    )
    assert recipe["build"]["test"] == []


@pytest.mark.parametrize(
    "param, result",
    [
        ({"test": [None, None, None]}, {"test": []}),
        ({"test": [None, "foo", None]}, {"test": ["foo"]}),
        ({"test": [None, "foo", None, "bar", None]}, {"test": ["foo", "bar"]}),
        ({"test": [None, "foo", None, "bar", None, None]}, {"test": ["foo", "bar"]}),
    ],
)
def test_remove_all_inner_none(param, result):
    assert remove_all_inner_nones(param) == result


def test_check_noarch_python_for_new_deps():
    config = Configuration(
        is_strict_cf=True, name="abcd", version="0.1.0", is_arch=True
    )
    check_noarch_python_for_new_deps(
        ["python >=3.6", "pip"],
        ["dataclasses >=3.6", "python >=3.6"],
        config,
    )
    assert config.is_arch is False
