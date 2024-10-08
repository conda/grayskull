"""Unit and integration tests for recipifying Poetry projects."""

import filecmp
from pathlib import Path

import pytest

from grayskull.main import generate_recipes_from_list, init_parser
from grayskull.strategy.py_toml import (
    add_flit_metadata,
    add_pep725_metadata,
    add_poetry_metadata,
    get_all_toml_info,
    get_constrained_dep,
)


def test_add_flit_metadata():
    metadata = {"build": {"entry_points": []}}
    toml_metadata = {"tool": {"flit": {"scripts": {"key": "value"}}}}
    result = add_flit_metadata(metadata, toml_metadata)
    assert result == {"build": {"entry_points": ["key = value"]}}


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
    args = parser.parse_args(
        ["pypi", "langchain==0.0.119", "-o", str(tmpdir), "-m", "AddYourGitHubIdHere"]
    )

    generate_recipes_from_list(args.pypi_packages, args)
    assert filecmp.cmp(snapshot_path, output_path, shallow=False)


def test_poetry_get_constrained_dep_version_not_present():
    assert (
        get_constrained_dep(
            {"git": "https://codeberg.org/hjacobs/pytest-kind.git"}, "pytest-kind"
        )
        == "pytest-kind"
    )


def test_poetry_entrypoints():
    poetry = {
        "requirements": {"host": ["setuptools"], "run": ["python"]},
        "build": {},
        "test": {},
    }
    toml_metadata = {
        "tool": {
            "poetry": {
                "scripts": {
                    "grayskull": "grayskull.main:main",
                    "grayskull-recipe": "grayskull.main:recipe",
                }
            }
        }
    }
    assert add_poetry_metadata(poetry, toml_metadata) == {
        "requirements": {
            "host": ["setuptools", "poetry-core"],
            "run": ["python"],
        },
        "build": {
            "entry_points": [
                "grayskull = grayskull.main:main",
                "grayskull-recipe = grayskull.main:recipe",
            ]
        },
        "test": {},
    }


@pytest.mark.parametrize(
    "conda_section, pep725_section",
    [("build", "build-requires"), ("host", "host-requires"), ("run", "dependencies")],
)
@pytest.mark.parametrize(
    "purl, purl_translated",
    [
        ("virtual:compiler/c", "{{ compiler('c') }}"),
        ("pkg:alice/bob", "pkg:alice/bob"),
    ],
)
def test_pep725_section_lookup(conda_section, pep725_section, purl, purl_translated):
    toml_metadata = {
        "external": {
            pep725_section: [purl],
        }
    }
    assert add_pep725_metadata({}, toml_metadata) == {
        "requirements": {conda_section: [purl_translated]}
    }
