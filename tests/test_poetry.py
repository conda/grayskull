"""Unit and integration tests for recipifying Poetry projects."""

import filecmp
from pathlib import Path

import pytest

from grayskull.__main__ import generate_recipes_from_list, init_parser
from grayskull.strategy.py_toml import (
    InvalidVersion,
    add_poetry_metadata,
    encode_poetry_version,
    get_all_toml_info,
    get_caret_ceiling,
    get_tilde_ceiling,
    parse_version,
)


@pytest.mark.parametrize(
    "version, major, minor, patch",
    [
        ("0", 0, None, None),
        ("1", 1, None, None),
        ("1.2", 1, 2, None),
        ("1.2.3", 1, 2, 3),
    ],
)
def test_parse_version_success(version, major, minor, patch):
    assert parse_version(version) == {"major": major, "minor": minor, "patch": patch}


@pytest.mark.parametrize("invalid_version", ["asdf", "", "."])
def test_parse_version_failure(invalid_version):
    with pytest.raises(InvalidVersion):
        parse_version(invalid_version)


@pytest.mark.parametrize(
    "version, ceiling_version",
    [
        ("0", "1.0.0"),
        ("0.0", "0.1.0"),
        ("0.0.3", "0.0.4"),
        ("0.2.3", "0.3.0"),
        ("1", "2.0.0"),
        ("1.2", "2.0.0"),
        ("1.2.3", "2.0.0"),
    ],
)
def test_get_caret_ceiling(version, ceiling_version):
    # examples from Poetry docs
    assert get_caret_ceiling(version) == ceiling_version


@pytest.mark.parametrize(
    "version, ceiling_version",
    [("1", "2.0.0"), ("1.2", "1.3.0"), ("1.2.3", "1.3.0")],
)
def test_get_tilde_ceiling(version, ceiling_version):
    # examples from Poetry docs
    assert get_tilde_ceiling(version) == ceiling_version


@pytest.mark.parametrize(
    "version, encoded_version",
    [
        # should be unchanged
        ("1.*", "1.*"),
        (">=1,<2", ">=1,<2"),
        ("==1.2.3", "==1.2.3"),
        ("!=1.2.3", "!=1.2.3"),
        # strip spaces
        (">= 1, < 2", ">=1,<2"),
        # handle exact version specifiers correctly
        ("1.2.3", "1.2.3"),
        ("==1.2.3", "==1.2.3"),
        # handle caret operator correctly
        # examples from Poetry docs
        ("^0", ">=0.0.0,<1.0.0"),
        ("^0.0", ">=0.0.0,<0.1.0"),
        ("^0.0.3", ">=0.0.3,<0.0.4"),
        ("^0.2.3", ">=0.2.3,<0.3.0"),
        ("^1", ">=1.0.0,<2.0.0"),
        ("^1.2", ">=1.2.0,<2.0.0"),
        ("^1.2.3", ">=1.2.3,<2.0.0"),
        # handle tilde operator correctly
        # examples from Poetry docs
        ("~1", ">=1.0.0,<2.0.0"),
        ("~1.2", ">=1.2.0,<1.3.0"),
        ("~1.2.3", ">=1.2.3,<1.3.0"),
    ],
)
def test_encode_poetry_version(version, encoded_version):
    assert encode_poetry_version(version) == encoded_version


def test_add_poetry_metadata():
    toml_metadata = {
        "tool": {
            "poetry": {
                "dependencies": {"tomli": ">=1.0.0", "requests": ">=1.0.0"},
                "group": {
                    "test": {"dependencies": {"tox": ">=1.0.0", "pytest": ">=1.0.0"}}
                },
            }
        }
    }
    metadata = {
        "requirements": {
            "host": ["pkg_host1 >=1.0.0", "pkg_host2"],
            "run": ["pkg_run1", "pkg_run2 >=2.0.0"],
        },
        "test": {"requires": ["mock", "pkg_test >=1.0.0"]},
    }
    assert add_poetry_metadata(metadata, toml_metadata) == {
        "requirements": {
            "host": ["pkg_host1 >=1.0.0", "pkg_host2", "poetry-core"],
            "run": [
                "pkg_run1",
                "pkg_run2 >=2.0.0",
                "tomli >=1.0.0",
                "requests >=1.0.0",
            ],
        },
        "test": {
            "requires": ["mock", "pkg_test >=1.0.0", "tox >=1.0.0", "pytest >=1.0.0"]
        },
    }


def test_poetry_dependencies():
    toml_path = Path(__file__).parent / "data" / "poetry" / "poetry.toml"
    result = get_all_toml_info(toml_path)

    assert result["test"]["requires"] == ["cachy 0.3.0", "deepdiff >=6.2.0,<7.0.0"]
    assert result["requirements"]["host"] == ["setuptools>=1.1.0", "poetry-core"]
    assert result["requirements"]["run"] == [
        "python >=3.7.0,<4.0.0",
        "cleo >=2.0.0,<3.0.0",
        "html5lib >=1.0.0,<2.0.0",
        "urllib3 >=1.26.0,<2.0.0",
    ]


def test_poetry_langchain_snapshot(tmpdir):
    """Snapshot test that asserts correct recipifying of an example Poetry project."""
    snapshot_path = (
        Path(__file__).parent / "data" / "poetry" / "langchain-expected.yaml"
    )
    output_path = tmpdir / "langchain" / "meta.yaml"

    parser = init_parser()
    args = parser.parse_args(["pypi", "langchain==0.0.119", "-o", str(tmpdir)])

    generate_recipes_from_list(args.pypi_packages, args)
    assert filecmp.cmp(snapshot_path, output_path, shallow=False)
