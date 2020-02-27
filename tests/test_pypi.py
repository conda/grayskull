import hashlib
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
    recipe = PyPi(name="pytest", version="5.3.1")
    pypi_reqs = recipe._extract_requirements(pypi_metadata["info"])
    assert sorted(pypi_reqs["host"]) == sorted(["python", "pip"])
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
            "colorama   # [win]",
        ]
    )


def test_get_pypi_metadata(pypi_metadata):
    metadata = PyPi._get_pypi_metadata(name="pytest", version="5.3.1")
    assert metadata["name"] == "pytest"
    assert metadata["version"] == "5.3.1"


def test_get_name_version_from_requires_dist():
    assert PyPi._get_name_version_from_requires_dist("py (>=1.5.0)") == (
        "py",
        ">=1.5.0",
    )


def test_get_extra_from_requires_dist():
    assert PyPi._get_extra_from_requires_dist(' python_version < "3.6"') == [
        ("", "python_version", "<", "3.6", "", "",)
    ]
    assert PyPi._get_extra_from_requires_dist(
        " python_version < \"3.6\" ; extra =='test'"
    ) == [
        ("", "python_version", "<", "3.6", "", ""),
        ("", "extra", "==", "test", "", ""),
    ]
    assert PyPi._get_extra_from_requires_dist(
        ' (sys_platform =="win32" and python_version =="2.7") and extra =="socks"'
    ) == [
        ("(", "sys_platform", "==", "win32", "", "and"),
        ("", "python_version", "==", "2.7", ")", "and"),
        ("", "extra", "==", "socks", "", ""),
    ]


def test_get_all_selectors_pypi():
    recipe = PyPi(name="pytest", version="5.3.1")
    assert recipe._get_all_selectors_pypi(
        [
            ("(", "sys_platform", "==", "win32", "", "and"),
            ("", "python_version", "==", "2.7", ")", "and"),
            ("", "extra", "==", "socks", "", ""),
        ]
    ) == ["(", "win", "and", "py==27", ")"]


def test_get_selector():
    assert PyPi._parse_extra_metadata_to_selector("extra", "==", "win32") == ""
    assert (
        PyPi._parse_extra_metadata_to_selector("sys_platform", "==", "win32") == "win"
    )
    assert (
        PyPi._parse_extra_metadata_to_selector("python_version", "<", "3.6") == "py<36"
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
    metadata = {"requires_python": requires_python}
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
    metadata = {"requires_python": requires_python}
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
    with pytest.raises(AttributeError) as err:
        PyPi.get_sha256_from_pypi_metadata(metadata)
    assert err.match("Hash information for sdist was not found on PyPi metadata.")


def test_injection_distutils():
    data = PyPi._get_sdist_metadata(
        "https://pypi.io/packages/source/h/hypothesis/hypothesis-5.5.1.tar.gz",
        "hypothesis",
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
    data = PyPi._get_sdist_metadata(
        "https://pypi.io/packages/source/p/pytest/pytest-5.3.2.tar.gz", "pytest"
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
        ["setuptools>=40.0", "setuptools_scm"]
    )
    assert not data.get("compilers")


def test_injection_distutils_compiler_gsw():
    data = PyPi._get_sdist_metadata(
        "https://pypi.io/packages/source/g/gsw/gsw-3.3.1.tar.gz", "gsw"
    )
    assert data.get("compilers") == ["c"]
    assert data["packages"] == ["gsw"]


def test_merge_pypi_sdist_metadata():
    pypi_metadata = PyPi._get_pypi_metadata(name="gsw", version="3.3.1")
    sdist_metadata = PyPi._get_sdist_metadata(pypi_metadata["sdist_url"], "gsw")
    merged_data = PyPi._merge_pypi_sdist_metadata(pypi_metadata, sdist_metadata)
    assert merged_data["compilers"] == ["c"]
    assert sorted(merged_data["setup_requires"]) == sorted(["numpy"])


def test_update_requirements_with_pin():
    req = {
        "build": ["<{ compiler('c') }}"],
        "host": ["python", "numpy"],
        "run": ["python", "numpy"],
    }
    PyPi._update_requirements_with_pin(req)
    assert req == {
        "build": ["<{ compiler('c') }}"],
        "host": ["python", "numpy"],
        "run": ["python", "<{ pin_compatible('numpy') }}"],
    }


def test_get_compilers():
    assert PyPi._get_compilers(["pybind11"], {}) == ["cxx"]
    assert PyPi._get_compilers(["cython"], {}) == ["c"]
    assert sorted(PyPi._get_compilers(["pybind11", "cython"], {})) == sorted(
        ["cxx", "c"]
    )
    assert sorted(PyPi._get_compilers(["pybind11"], {"compilers": ["c"]})) == sorted(
        ["cxx", "c"]
    )


def test_get_entry_points_from_sdist():
    assert PyPi._get_entry_points_from_sdist({}) == []
    assert PyPi._get_entry_points_from_sdist(
        {"entry_points": {"console_scripts": ["console_scripts=entrypoints"]}}
    ) == ["console_scripts=entrypoints"]
    assert PyPi._get_entry_points_from_sdist(
        {"entry_points": {"gui_scripts": ["gui_scripts=entrypoints"]}}
    ) == ["gui_scripts=entrypoints"]

    assert sorted(
        PyPi._get_entry_points_from_sdist(
            {
                "entry_points": {
                    "gui_scripts": ["gui_scripts=entrypoints"],
                    "console_scripts": ["console_scripts=entrypoints"],
                }
            }
        )
    ) == sorted(["gui_scripts=entrypoints", "console_scripts=entrypoints"])


def test_build_noarch_skip():
    recipe = PyPi(name="hypothesis", version="5.5.2")
    assert recipe["build"]["noarch"].values[0] == "python"
    assert not recipe["build"]["skip"].values


def test_run_requirements_sdist():
    recipe = PyPi(name="botocore", version="1.14.17")
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
    assert sorted(
        PyPi._format_dependencies(["setuptools>=40.0", "pkg2"], "pkg1")
    ) == sorted(["setuptools >=40.0", "pkg2"])
    assert sorted(
        PyPi._format_dependencies(["setuptools>=40.0", "pkg2"], "pkg2")
    ) == sorted(["setuptools >=40.0"])
    assert sorted(PyPi._format_dependencies(["setuptools >= 40.0"], "pkg")) == sorted(
        ["setuptools >=40.0"]
    )
    assert sorted(
        PyPi._format_dependencies(["setuptools_scm [toml] >=3.4.1"], "pkg")
    ) == sorted(["setuptools_scm >=3.4.1"])


def test_download_pkg_sdist(pkg_pytest):
    with open(pkg_pytest, "rb") as pkg_file:
        content = pkg_file.read()
        pkg_sha256 = hashlib.sha256(content).hexdigest()
    assert (
        pkg_sha256 == "0d5fe9189a148acc3c3eb2ac8e1ac0742cb7618c084f3d228baaec0c254b318d"
    )
    setup_cfg = PyPi._get_setup_cfg(os.path.dirname(pkg_pytest))
    assert setup_cfg["name"] == "pytest"
    assert setup_cfg["python_requires"] == ">=3.5"
    assert setup_cfg["entry_points"] == {
        "console_scripts": ["pytest=pytest:main", "py.test=pytest:main"]
    }


def test_ciso_recipe():
    recipe = PyPi(name="ciso", version="0.1.0")
    assert sorted(recipe["requirements"]["host"]) == sorted(
        ["cython", "numpy", "pip", "python", "versioneer"]
    )
    assert sorted(recipe["requirements"]["run"]) == sorted(
        ["cython", "python", "<{ pin_compatible('numpy') }}"]
    )
    assert recipe["test"]["commands"] == "pip check"
    assert recipe["test"]["requires"] == "pip"
    assert recipe["test"]["imports"] == "ciso"


def test_pymc_recipe_fortran():
    recipe = PyPi(name="pymc", version="2.3.6")
    assert sorted(recipe["requirements"]["build"]) == sorted(
        ["<{ compiler('c') }}", "<{ compiler('fortran') }}"]
    )
    assert sorted(recipe["requirements"]["host"]) == sorted(["numpy", "python", "pip"])
    assert sorted(recipe["requirements"]["run"]) == sorted(
        ["<{ pin_compatible('numpy') }}", "python"]
    )
    assert not recipe["build"]["noarch"]


def test_pytest_recipe_entry_points():
    recipe = PyPi(name="pytest", version="5.3.5")
    assert sorted(recipe["build"]["entry_points"]) == sorted(
        ["pytest=pytest:main", "py.test=pytest:main"]
    )
    assert recipe["about"]["license"] == "MIT"
    assert recipe["about"]["license_file"] == "LICENSE"
    assert recipe["build"]["skip"].values[0].value
    assert recipe["build"]["skip"].values[0].selector == "py2k"
    assert not recipe["build"]["noarch"]


def test_cythongsl_recipe_build():
    recipe = PyPi(name="cythongsl", version="0.2.2")
    assert recipe["requirements"]["build"] == "<{ compiler('c') }}"
    assert recipe["requirements"]["host"] == ["cython >=0.16", "pip", "python"]
    assert not recipe["build"]["noarch"]


def test_requests_recipe_extra_deps():
    recipe = PyPi(name="requests", version="2.22.0")
    assert "win-inet-pton" not in recipe["requirements"]["run"]
    assert recipe["build"]["noarch"]
    assert not recipe["build"]["skip"]


def test_zipp_recipe_tags_on_deps():
    recipe = PyPi(name="zipp", version="3.0.0")
    assert recipe["build"]["noarch"]
    assert recipe["requirements"]["host"] == [
        "pip",
        "python >=3.6",
        "setuptools_scm >=3.4.1",
    ]


def test_generic_py_ver_to():
    assert PyPi._generic_py_ver_to({"requires_python": ">=3.5, <3.8"}) == ">=3.6,<3.8"


def test_botocore_recipe_license_name():
    recipe = PyPi(name="botocore", version="1.15.8")
    assert recipe["about"]["license"] == "Apache-2.0"
