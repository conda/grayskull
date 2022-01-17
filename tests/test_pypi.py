import hashlib
import json
import os
import sys

import pytest
from colorama import Fore, Style
from souschef.recipe import Recipe

from grayskull.__main__ import create_python_recipe
from grayskull.base.factory import GrayskullFactory
from grayskull.base.pkg_info import normalize_pkg_name
from grayskull.cli import CLIConfig
from grayskull.cli.parser import parse_pkg_name_version
from grayskull.config import Configuration
from grayskull.strategy.py_base import (
    clean_deps_for_conda_forge,
    ensure_pep440,
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
    extract_requirements,
    get_all_selectors_pypi,
    get_pypi_metadata,
    get_sha256_from_pypi_metadata,
    get_url_filename,
    merge_pypi_sdist_metadata,
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
def recipe_config():
    config = Configuration(name="pytest")
    recipe = Recipe(name="pytest")
    return recipe, config


def test_extract_pypi_requirements(pypi_metadata, recipe_config):
    recipe, config = recipe_config
    pypi_reqs = extract_requirements(pypi_metadata["info"], config, recipe)
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


def test_get_all_selectors_pypi(recipe_config):
    _, config = recipe_config
    config.version = "5.3.1"
    assert (
        get_all_selectors_pypi(
            [
                ("(", "sys_platform", "==", "win32", "", "and"),
                ("", "python_version", "==", "2.7", ")", "and"),
                ("", "extra", "==", "socks", "", ""),
            ],
            config,
        )
        == ["(", "win", "and", "py==27", ")"]
    )


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
        ["setuptools>=40.0", "setuptools_scm"]
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

    assert (
        sorted(
            get_entry_points_from_sdist(
                {
                    "entry_points": {
                        "gui_scripts": ["gui_scripts=entrypoints"],
                        "console_scripts": ["console_scripts=entrypoints"],
                    }
                }
            )
        )
        == sorted(["gui_scripts=entrypoints", "console_scripts=entrypoints"])
    )
    assert (
        sorted(
            get_entry_points_from_sdist(
                {
                    "entry_points": {
                        "gui_scripts": None,
                        "console_scripts": "console_scripts=entrypoints",
                    }
                }
            )
        )
        == sorted(["console_scripts=entrypoints"])
    )
    assert (
        sorted(
            get_entry_points_from_sdist(
                {
                    "entry_points": {
                        "gui_scripts": None,
                        "console_scripts": "console_scripts=entrypoints\nfoo=bar.main",
                    }
                }
            )
        )
        == sorted(["console_scripts=entrypoints", "foo=bar.main"])
    )
    assert (
        sorted(
            get_entry_points_from_sdist(
                {
                    "entry_points": {
                        "gui_scripts": "gui_scripts=entrypoints",
                        "console_scripts": None,
                    }
                }
            )
        )
        == sorted(["gui_scripts=entrypoints"])
    )


@pytest.mark.parametrize(
    "name", ["hypothesis=5.5.2", "https://github.com/HypothesisWorks/hypothesis"]
)
def test_build_noarch_skip(name):
    recipe = create_python_recipe(name)[0]
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
    assert sorted(recipe["requirements"]["build"]) == sorted(
        ["<{ compiler('c') }}", "<{ compiler('fortran') }}"]
    )
    assert sorted(recipe["requirements"]["host"]) == sorted(["numpy", "python", "pip"])
    assert sorted(recipe["requirements"]["run"]) == sorted(
        ["<{ pin_compatible('numpy') }}", "python"]
    )
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
    assert recipe["requirements"]["host"] == ["cython >=0.16", "pip", "python"]
    assert recipe["build"]["noarch"] is None


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
    assert recipe["requirements"]["host"] == [
        "pip",
        "python >=3.6",
        "setuptools-scm >=3.4.1",
    ]


def test_generic_py_ver_to():
    config = Configuration(name="abc")
    assert generic_py_ver_to({"requires_python": ">=3.5, <3.8"}, config) == ">=3.5,<3.8"


def test_botocore_recipe_license_name():
    config = Configuration(name="botocore", version="1.15.8")
    recipe = GrayskullFactory.create_recipe("pypi", config)
    assert recipe["about"]["license"] == "Apache-2.0"


def test_ipytest_recipe_license():
    config = Configuration(name="ipytest", version="0.8.0")
    recipe = GrayskullFactory.create_recipe("pypi", config)
    assert recipe["about"]["license"] == "MIT"


def test_get_test_entry_points():
    assert get_test_entry_points("grayskull = grayskull.__main__:main") == [
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
    assert recipe["about"]["license"] == "BSD-3-Clause"
    assert recipe["about"]["license_file"] == "LICENSE"
    assert recipe["test"]["imports"][0] == "rest_framework_xml"


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
    assert recipe["requirements"]["run"] == [
        "aiohttp >=2.3.10,<4.0.0",
        "certifi >=14.05.14",
        "python",
        "python-dateutil >=2.5.3",
        "pyyaml >=3.12",
        "setuptools >=21.0.0",
        "six >=1.9.0",
        "urllib3 >=1.24.2",
    ]


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


def test_sequence_inside_another_in_dependencies():
    recipe = create_python_recipe("unittest2=1.1.0", is_strict_cf=True)[0]
    assert recipe["requirements"]["host"] == [
        "argparse",
        "pip",
        "python >=3.6",
        "six >=1.4",
        "traceback2",
    ]
    assert recipe["requirements"]["run"] == [
        "argparse",
        "python >=3.6",
        "six >=1.4",
        "traceback2",
    ]


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


def test_add_python_min_to_strict_conda_forge():
    recipe = create_python_recipe("dgllife=0.2.8", is_strict_cf=True)[0]
    assert recipe["build"]["noarch"] == "python"
    assert recipe["requirements"]["host"][1] == "python >=3.6"
    assert "python >=3.6" in recipe["requirements"]["run"]


def test_get_test_imports_clean_modules():
    assert (
        get_test_imports(
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
        )
        == ["pytest", "zar"]
    )
    assert (
        get_test_imports(
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
        )
        == ["_pytest", "_pytest._code"]
    )


def test_ensure_pep440():
    assert ensure_pep440("pytest ~=5.3.2") == "pytest >=5.3.2,==5.3.*"


def test_pep440_recipe():
    recipe = create_python_recipe("codalab=0.5.26", is_strict_cf=False)[0]
    assert recipe["requirements"]["host"] == ["pip", "python >=3.6,<3.7"]


def test_pep440_in_recipe_pypi():
    recipe = create_python_recipe("kedro=0.17.6", is_strict_cf=False)[0]
    assert sorted(recipe["requirements"]["run"])[0] == "anyconfig >=0.10.0,==0.10.*"
