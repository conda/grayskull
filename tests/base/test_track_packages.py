from pathlib import Path

import pytest

from grayskull.base.track_packages import (
    ConfigPkg,
    _get_track_info_from_file,
    _version_solver,
    parse_delimiter,
    solve_list_pkg_name,
    solve_pkg_name,
    solve_version_delimiter,
    track_package,
)


@pytest.fixture
def path_example() -> Path:
    return Path(__file__).parent.parent / "data" / "track_package" / "example.yaml"


def test_config_pkg():
    cfg = ConfigPkg("name", "import_name", "conda_forge", "min", "max")
    assert cfg.name == "name"
    assert cfg.import_name == "import_name"
    assert cfg.conda_forge == "conda_forge"
    assert cfg.delimiter_min == "min"
    assert cfg.delimiter_max == "max"

    cfg = ConfigPkg("name")
    assert cfg.name == "name"
    assert cfg.import_name == "name"
    assert cfg.conda_forge == "name"
    assert cfg.delimiter_min == ""
    assert cfg.delimiter_max == ""


def test_track_package(path_example: Path):
    foo_pkg = track_package("foo_pkg", path_example)
    assert foo_pkg.name == "foo_pkg"
    assert foo_pkg.import_name == "foo_import"
    assert foo_pkg.conda_forge == "foo_conda_forge"
    assert foo_pkg.delimiter_min == "1.2.3"
    assert foo_pkg.delimiter_max == "2.1.0"

    bar_pkg = track_package("bar_pkg", path_example)
    assert bar_pkg.name == "bar_pkg"
    assert bar_pkg.import_name == "bar_import"
    assert bar_pkg.conda_forge == "bar_conda_forge"
    assert bar_pkg.delimiter_min == ""
    assert bar_pkg.delimiter_max == ""

    foo_bar_pkg = track_package("foo_bar", path_example)
    assert foo_bar_pkg.name == "foo_bar"
    assert foo_bar_pkg.import_name == "foo_bar"
    assert foo_bar_pkg.conda_forge == "foo_bar_cf"
    assert foo_bar_pkg.delimiter_min == ""
    assert foo_bar_pkg.delimiter_max == ""

    no_pkg = track_package("NO_PKG", path_example)
    assert no_pkg.name == "NO_PKG"
    assert no_pkg.import_name == "NO_PKG"
    assert no_pkg.conda_forge == "NO_PKG"
    assert no_pkg.delimiter_min == ""
    assert no_pkg.delimiter_max == ""


def test_get_track_info_from_file(path_example):
    dict_exp = {
        "foo_pkg": {
            "import_name": "foo_import",
            "conda_forge": "foo_conda_forge",
            "delimiter_min": "1.2.3",
            "delimiter_max": "2.1.0",
        },
        "bar_pkg": {"import_name": "bar_import", "conda_forge": "bar_conda_forge"},
        "foo_bar": {"conda_forge": "foo_bar_cf"},
    }
    assert _get_track_info_from_file(path_example) == dict_exp
    assert _get_track_info_from_file(str(path_example)) == dict_exp


def test_parse_delimiter():
    assert parse_delimiter("<1.0.0,>2.0.0") == [("<", "1.0.0"), (">", "2.0.0")]
    assert parse_delimiter("<=1.0.0,>=2.0.0") == [("<=", "1.0.0"), (">=", "2.0.0")]
    assert parse_delimiter("!=1.0.0, >2.0.0") == [("!=", "1.0.0"), (">", "2.0.0")]
    assert parse_delimiter("==2.0.0") == [("==", "2.0.0")]


def test_solve_version_delimiter():
    assert (
        solve_version_delimiter(
            "pkg >=1.5.0,<1.8.0",
            ConfigPkg("foo", delimiter_min="1.0.0", delimiter_max="2.0.0"),
        )
        == ">=1.5.0,<1.8.0"
    )
    assert (
        solve_version_delimiter(
            ">0.5.0,<=1.8.0",
            ConfigPkg("foo", delimiter_min="1.0.0", delimiter_max="2.0.0"),
        )
        == ">=1.0.0,<=1.8.0"
    )
    assert (
        solve_version_delimiter(
            ">0.5.0,<2.5.0",
            ConfigPkg("foo", delimiter_min="1.0.0", delimiter_max="2.0.0"),
        )
        == ">=1.0.0,<2.0.0"
    )
    assert (
        solve_version_delimiter(
            "1.2.3", ConfigPkg("foo", delimiter_min="1.0.0", delimiter_max="2.0.0")
        )
        == "1.2.3"
    )
    assert (
        solve_version_delimiter(
            ">=1.5.0,<2.5.0,!=1.6.3",
            ConfigPkg("foo", delimiter_min="1.0.0", delimiter_max="2.0.0"),
        )
        == ">=1.5.0,<2.0.0,!=1.6.3"
    )


def test_version_solver():
    assert (
        _version_solver(
            [(">=", "1.5.0"), ("<", "1.8.0")],
            ConfigPkg("foo", delimiter_min="1.0.0", delimiter_max="2.0.0"),
        )
        == [">=1.5.0", "<1.8.0"]
    )
    assert (
        _version_solver(
            [(">", "0.5.0"), ("<=", "1.8.0")],
            ConfigPkg("foo", delimiter_min="1.0.0", delimiter_max="2.0.0"),
        )
        == [">=1.0.0", "<=1.8.0"]
    )


def test_solve_pkg_name(path_example):
    assert (
        solve_pkg_name("foo_pkg >1.5.0,<=2.5.0", path_example)
        == "foo_conda_forge >1.5.0,<2.1.0"
    )
    assert solve_pkg_name("normal_pkg", path_example) == "normal_pkg"


def test_solve_list_pkg_name(path_example):
    assert solve_list_pkg_name(
        ["foo_pkg >1.5.0,<=2.5.0", "normal_pkg", "bar_pkg"], path_example
    ) == ["foo_conda_forge >1.5.0,<2.1.0", "normal_pkg", "bar_conda_forge"]
