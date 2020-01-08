import json
import os

import pytest

from grayskull.pypi import PyPi


@pytest.fixture
def pypi_metadata():
    path_metadata = os.path.join(
        os.path.dirname(__file__), "data", "pypi_pytest_metadata.json"
    )
    with open(path_metadata) as f:
        return json.load(f)


def test_extract_pypi_requirements(pypi_metadata):
    recipe = PyPi(name="pytest")
    pypi_reqs = recipe._extract_pypi_requirements(pypi_metadata)
    assert sorted(pypi_reqs.host) == sorted(["python", "pip"])
    assert sorted(pypi_reqs.run) == sorted(
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
            "colorama   # [win]",
        ]
    )


def test_get_pypi_metadata(pypi_metadata):
    recipe = PyPi(name="pytest", version="5.3.1")
    metadata = recipe._get_pypi_metadata()
    assert metadata["package"].name == "pytest"
    assert metadata["package"].version == "5.3.1"
    assert metadata["test"].imports == ["pytest"]


def test_get_name_version_from_requires_dist():
    assert PyPi._get_name_version_from_requires_dist("py (>=1.5.0)") == (
        "py",
        ">=1.5.0",
    )


def test_get_extra_from_requires_dist():
    assert PyPi._get_extra_from_requires_dist(' python_version < "3.6"') == (
        "python_version",
        "<",
        "3.6",
    )


def test_get_selector():
    assert PyPi._parse_extra_metadata_to_selector("extra", "==", "win32") == ""
    assert (
        PyPi._parse_extra_metadata_to_selector("sys_platform", "==", "win32")
        == "  # [win]"
    )
    assert (
        PyPi._parse_extra_metadata_to_selector("python_version", "<", "3.6")
        == "  # [py<36]"
    )


@pytest.mark.parametrize(
    "requires_python, exp_selector",
    [
        (">=3.5", "2k"),
        (">=3.6", "2k"),
        (">=3.7", "<37"),
        ("<=3.7", ">=38"),
        ("<=3.7.1", ">=38"),
        ("<3.7", ">=37"),
        (">2.7, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*, !=3.4.*", "2k"),
        (">=2.7, !=3.6.*", "==36"),
        (">3.7", "<38"),
        (">2.7", "2k"),
        ("<3", "3k"),
        ("!=3.7", "==37"),
    ],
)
def test_py_version_to_selector(requires_python, exp_selector):
    metadata = {"info": {"requires_python": requires_python}}
    assert PyPi.py_version_to_selector(metadata) == f"# [py{exp_selector}]"


@pytest.mark.parametrize(
    "requires_python, exp_limit",
    [
        (">=3.5", ">=3.6"),
        (">=3.6", ">=3.6"),
        (">=3.7", ">=3.7"),
        ("<=3.7", "<3.8"),
        ("<=3.7.1", "<3.8"),
        ("<3.7", "<3.7"),
        (">2.7, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*, !=3.4.*", ">=3.6"),
        (">=2.7, !=3.6.*", "!=3.6"),
        (">3.7", ">=3.8"),
        (">2.7", ">=3.6"),
        ("<3", "<3.0"),
        ("!=3.7", "!=3.7"),
    ],
)
def test_py_version_to_limit_python(requires_python, exp_limit):
    metadata = {"info": {"requires_python": requires_python}}
    assert PyPi.py_version_to_limit_python(metadata) == f"{exp_limit}"


def test_get_sha256_from_pypi_metadata():
    metadata = {
        "urls": [
            {"packagetype": "egg", "digests": {"sha256": "23123"}},
            {"packagetype": "sdist", "digests": {"sha256": "1234sha256"}},
        ]
    }
    assert PyPi.get_sha256_from_pypi_metadata(metadata) == "1234sha256"

    metadata = {
        "urls": [
            {"packagetype": "egg", "digests": {"sha256": "23123"}},
            {"packagetype": "wheel", "digests": {"sha256": "1234sha256"}},
        ]
    }
    with pytest.raises(ValueError) as err:
        PyPi.get_sha256_from_pypi_metadata(metadata)
    assert err.match("Hash information for sdist was not found on PyPi metadata.")
